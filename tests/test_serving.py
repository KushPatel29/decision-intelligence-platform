"""Serving integrity holds at read time, including after cached startup checks."""

import hashlib
import json

import pytest

from decision_platform.serving import read_verified, verify_manifest


def publish(folder, files):
    manifest = {
        "files": files,
        "release_id": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
    }
    (folder / "manifest.json").write_text(json.dumps(manifest))
    return manifest


def test_late_read_rejects_bytes_changed_after_verification(tmp_path):
    path = tmp_path / "summary.json"
    path.write_bytes(b'{"customers": 3}')
    publish(tmp_path, {path.name: hashlib.sha256(path.read_bytes()).hexdigest()})
    manifest = verify_manifest(tmp_path, [path.name])
    path.write_bytes(b'{"customers": 999}')
    with pytest.raises(ValueError, match="integrity"):
        read_verified(tmp_path, manifest, path.name)


def test_existing_unlisted_file_is_not_read(tmp_path):
    (tmp_path / "rogue.json").write_text("{}")
    manifest = publish(tmp_path, {})
    with pytest.raises(ValueError, match="Unlisted"):
        read_verified(tmp_path, manifest, "rogue.json")


def test_manifest_rejects_path_traversal(tmp_path):
    publish(tmp_path, {"../outside.json": "0" * 64})
    with pytest.raises(ValueError, match="unsafe"):
        verify_manifest(tmp_path, [])


def test_manifest_rejects_release_id_mismatch(tmp_path):
    manifest = publish(tmp_path, {})
    manifest["release_id"] = "0" * 64
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="release ID"):
        verify_manifest(tmp_path, [])


def test_streamlit_loader_rechecks_after_cached_verification(tmp_path, monkeypatch):
    from decision_platform import webapp

    for name in webapp.REQUIRED:
        (tmp_path / name).write_bytes(b"{}")
    files = {name: hashlib.sha256(b"{}").hexdigest() for name in webapp.REQUIRED}
    publish(tmp_path, files)
    monkeypatch.setattr(webapp, "SERVING", tmp_path)
    webapp.verify_snapshot.clear()
    webapp._doc.clear()
    try:
        stamp = webapp.snapshot_stamp()
        webapp.verify_snapshot(stamp)
        (tmp_path / "summary.json").write_text('{"changed": true}')
        with pytest.raises(ValueError, match="integrity"):
            webapp._doc("summary", stamp)
    finally:
        webapp.verify_snapshot.clear()
        webapp._doc.clear()


def test_shipped_snapshot_matches_its_manifest():
    from decision_platform.config import ROOT

    folder = ROOT / "outputs" / "serving"
    verify_manifest(
        folder,
        ["summary.json", "customers.parquet", "candidates.parquet", "decisions.parquet", "capacity.parquet"],
    )
