"""Fail-closed artifact serving, exclusive pipeline runs and persistent decision audit."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid
import threading
from functools import wraps
from .config import write_json

_solve_slots=threading.BoundedSemaphore(2)
def bounded_operation(function):
    @wraps(function)
    def wrapped(*args,**kwargs):
        if not _solve_slots.acquire(timeout=.1):raise RuntimeError("Both optimization workers are busy. Retry after a current solve finishes.")
        try:return function(*args,**kwargs)
        finally:_solve_slots.release()
    return wrapped

def now():
    return datetime.now(timezone.utc).isoformat()

def artifact_manifest(root):
    folder = Path(root)/"outputs"
    candidates=list(folder.iterdir())
    for name in ["powerbi","performance","adhoc","models"]:
        if (folder/name).exists():candidates.extend((folder/name).rglob("*"))
    files = [p for p in candidates if p.is_file() and p.suffix in {".csv", ".json"}
             and p.name not in {"artifact_manifest.json", "run_status.json", "repro_reference.json"}]
    hashes = {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
    value = {"schema_version": 1, "created_at": now(), "files": hashes}
    value["release_id"] = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    write_json(folder/"artifact_manifest.json", value)
    return value

def validate_release(root):
    root = Path(root)
    if (root/".pipeline.lock").exists():
        raise ValueError("A data refresh is running. Decisions are paused until the complete release is validated.")
    status = root/"outputs/run_status.json"
    if status.exists() and json.loads(status.read_text())["status"] != "complete":
        raise ValueError("The latest data refresh did not complete. Restore the previous release or rerun the pipeline.")
    manifest = root/"outputs/artifact_manifest.json"
    if not manifest.exists():
        return {"status": "legacy", "release_id": "unverified"}
    value = json.loads(manifest.read_text())
    for name, digest in value["files"].items():
        path = (root/"outputs"/name).resolve()
        if not path.is_relative_to((root/"outputs").resolve()) or not path.is_file():
            raise ValueError("Release contains a missing or invalid artifact")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Release integrity check failed for {name}. Restore a verified release.")
    return {"status": "verified", **value}

@contextmanager
def pipeline_run(cfg):
    cfg.path("outputs").mkdir(parents=True, exist_ok=True)
    lock = cfg.path(".pipeline.lock")
    try:
        descriptor = os.open(lock, os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError as exc:
        raise RuntimeError("Another pipeline owns the run lock. Inspect run_status before recovering a stale lock.") from exc
    run_id = uuid.uuid4().hex
    os.write(descriptor, json.dumps({"pid": os.getpid(), "run_id": run_id, "started_at": now()}).encode())
    os.close(descriptor)
    write_json(cfg.path("outputs", "run_status.json"), {"status": "running", "run_id": run_id, "started_at": now()})
    try:
        yield run_id
        artifact_manifest(cfg.root)
        write_json(cfg.path("outputs", "run_status.json"), {"status": "complete", "run_id": run_id, "completed_at": now()})
    except BaseException:
        write_json(cfg.path("outputs", "run_status.json"), {"status": "failed", "run_id": run_id, "failed_at": now(), "recovery": "Rerun successfully or restore the last release; do not serve partial artifacts"})
        raise
    finally:
        lock.unlink(missing_ok=True)

def audit_event(root, owner, action, payload):
    folder = Path(root)/"runtime"
    folder.mkdir(parents=True, exist_ok=True)
    identifier = uuid.uuid4().hex
    with sqlite3.connect(folder/"decisions.sqlite", timeout=10) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, owner TEXT NOT NULL, action TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL)")
        db.execute("INSERT INTO events VALUES (?,?,?,?,?)", (identifier, owner, action, now(), json.dumps(payload, allow_nan=False, default=str)))
    return identifier

def saved_plans(root, owner):
    path = Path(root)/"runtime/decisions.sqlite"
    if not path.exists():
        return []
    with sqlite3.connect(path, timeout=10) as db:
        rows = db.execute("SELECT id, created_at, payload FROM events WHERE owner=? AND action='save_plan' ORDER BY created_at DESC LIMIT 20", (owner,)).fetchall()
    return [{"id": r[0], "saved_at": r[1], **json.loads(r[2])} for r in rows]
