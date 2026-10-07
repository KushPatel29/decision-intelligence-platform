"""Shared state for the Streamlit views: the verified serving snapshot and request context.

`app.py` validates the release once per snapshot and stores the context in
session state; every view reads tables and documents through these cached
loaders, so a page never touches files the release manifest did not hash.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import streamlit as st

from .config import ROOT

SERVING = Path(os.environ.get("CORRIDOR_SERVING", ROOT / "outputs" / "serving"))
REQUIRED = [
    "summary.json",
    "optimization.json",
    "policy_value.json",
    "customers.parquet",
    "decisions.parquet",
    "candidates.parquet",
    "capacity.parquet",
]


# Live re-solves are CPU-bound and every session shares this process: at most CORRIDOR_MAX_SOLVES run at once,
# each MIP sub-solve capped at CORRIDOR_SOLVE_SECONDS, the same limits the decision API uses.
SOLVE_SECONDS = float(os.environ.get("CORRIDOR_SOLVE_SECONDS", "20"))
_SOLVER_SLOTS = threading.BoundedSemaphore(max(1, int(os.environ.get("CORRIDOR_MAX_SOLVES", "2"))))


@contextmanager
def solver_slot():
    """Yield True while holding a solver slot, or False at once when every slot is busy."""
    acquired = _SOLVER_SLOTS.acquire(blocking=False)
    try:
        yield acquired
    finally:
        if acquired:
            _SOLVER_SLOTS.release()


def snapshot_stamp():
    manifest = SERVING / "manifest.json"
    return manifest.stat().st_mtime_ns if manifest.exists() else None


@st.cache_resource(show_spinner=False)
def verify_snapshot(stamp):
    """Check every serving file against the snapshot manifest; raise on any mismatch."""
    manifest = json.loads((SERVING / "manifest.json").read_text())
    for name, digest in manifest["files"].items():
        path = (SERVING / name).resolve()
        if not path.is_relative_to(SERVING.resolve()) or not path.is_file():
            raise ValueError(f"Serving snapshot is missing {name}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Serving snapshot integrity check failed for {name}")
    missing = [name for name in REQUIRED if name not in manifest["files"]]
    if missing:
        raise ValueError(f"Serving snapshot is incomplete: {missing}")
    return manifest


@st.cache_data(show_spinner=False, max_entries=64)
def _table(name, stamp):
    return pd.read_parquet(SERVING / f"{name}.parquet")


@st.cache_data(show_spinner=False, max_entries=64)
def _doc(name, stamp):
    return json.loads((SERVING / f"{name}.json").read_text(encoding="utf-8"))


def context():
    return st.session_state["corridor"]


def table(name):
    return _table(name, context()["stamp"]).copy()


def doc(name):
    return _doc(name, context()["stamp"])


def has(name):
    return (SERVING / name).exists()


def zone_names():
    return dict(zip(table("zones").zone_id.astype(int), table("zones").zone_name, strict=True))


def offers():
    return table("offers")


def offer_names():
    frame = offers()
    return dict(zip(frame.offer_id, frame.offer_name, strict=True))


def offer_order():
    return offers().offer_id.tolist()


def download(frame, name, label="Download CSV"):
    st.download_button(
        label, frame.to_csv(index=False).encode(), file_name=name, mime="text/csv", key="download_" + name
    )
