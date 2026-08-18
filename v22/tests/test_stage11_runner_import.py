from __future__ import annotations
from pathlib import Path
import os
import subprocess
import sys

def test_runner_imports_v22_from_arbitrary_cwd(tmp_path):
    repo = Path(__file__).resolve().parents[2]
    runner = repo / "scripts" / "v22_paper_competition.py"
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    # DATABASE_URL is intentionally omitted: reaching that validation proves all
    # imports succeeded without needing a real database.
    proc = subprocess.run(
        [sys.executable, str(runner)],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
    )
    combined = proc.stdout + proc.stderr
    assert "ModuleNotFoundError" not in combined
    assert "DATABASE_URL is required" in combined
