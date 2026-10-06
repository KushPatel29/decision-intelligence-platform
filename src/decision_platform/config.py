from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import json
import platform
import subprocess
import importlib.metadata
import os
import tempfile

ROOT = Path(os.environ.get("CORRIDOR_ROOT", Path(__file__).resolve().parents[2])).resolve()

@dataclass(frozen=True)
class Config:
    seed: int = 407
    customers: int = 8000
    start: str = "2024-01-01"
    end: str = "2025-12-31"
    decision_date: str = "2025-10-01"
    budget: float = 1600.0
    campaign_limit: int = 180
    min_roi: float = 0.15  # Net incremental contribution / incentive cost.
    contribution_margin: float = 0.72
    root: Path = ROOT

    def path(self, *parts):
        return self.root.joinpath(*parts)

def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, default=str, allow_nan=False)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

def frame_hash(frame):
    import pandas as pd
    return hashlib.sha256(pd.util.hash_pandas_object(frame, index=True).values.tobytes()).hexdigest()

def manifest(cfg, frames):
    try:
        sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=cfg.root, stderr=subprocess.DEVNULL, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        sha = "uncommitted"
    versions = {p: importlib.metadata.version(p) for p in ["numpy", "pandas", "scipy", "scikit-learn", "duckdb", "pyarrow"]}
    return {"config": asdict(cfg), "git_sha": sha, "python": platform.python_version(),
            "packages": versions, "datasets": {k: {"rows": len(v), "sha256": frame_hash(v)} for k,v in frames.items()}}
