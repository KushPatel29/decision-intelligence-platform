"""Read only bytes authenticated by a complete serving manifest."""

import hashlib
import json
from pathlib import Path


def read_verified(folder: Path, manifest: dict, name: str) -> bytes:
    path = (folder / name).resolve()
    if name not in manifest["files"] or not path.is_relative_to(folder.resolve()):
        raise ValueError(f"Unlisted or unsafe serving file: {name}")
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != manifest["files"][name]:
        raise ValueError(f"Serving snapshot integrity check failed for {name}")
    return payload


def verify_manifest(folder: Path, required) -> dict:
    manifest = json.loads((folder / "manifest.json").read_bytes())
    files = manifest["files"]
    if not isinstance(files, dict):
        raise ValueError("Invalid serving file manifest")
    missing = sorted(set(required) - files.keys())
    if missing:
        raise ValueError(f"Serving snapshot is incomplete: {missing}")
    release = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    if release != manifest["release_id"]:
        raise ValueError("Serving release ID does not match its file manifest")
    for name in files:
        read_verified(folder, manifest, name)
    return manifest
