#!/usr/bin/env python3
"""Build the V22 AWS Lambda deployment package.

By default this builds a dependency-free source rehearsal ZIP. Pass --install-deps
on Linux/GitHub Actions to install the Python 3.12 Linux psycopg binary wheel into
the ZIP as required by the real Lambda deployment.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def copy_tree(src: Path, dst: Path) -> None:
    def ignore(_dir, names):
        blocked = {"__pycache__", ".pytest_cache", "tests"}
        return [n for n in names if n in blocked or n.endswith((".pyc", ".pyo"))]
    shutil.copytree(src, dst, ignore=ignore)


def build(out: Path, install_deps: bool) -> Path:
    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="v22-lambda-") as tmp:
        stage = Path(tmp) / "package"
        stage.mkdir()
        copy_tree(ROOT / "v22", stage / "v22")
        (stage / "config").mkdir()
        shutil.copy2(ROOT / "config" / "v22_live_assets.json", stage / "config" / "v22_live_assets.json")
        if install_deps:
            cmd = [
                sys.executable, "-m", "pip", "install",
                "--disable-pip-version-check", "--no-compile",
                "--platform", "manylinux2014_x86_64",
                "--implementation", "cp",
                "--python-version", "3.12",
                "--only-binary=:all:",
                "--target", str(stage),
                "psycopg[binary]>=3.2,<4",
            ]
            subprocess.run(cmd, check=True)
        # Lambda requires package contents at ZIP root, not inside a parent folder.
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(stage.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(stage))
    return out


def inspect(path: Path, require_deps: bool) -> None:
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        required = {
            "v22/runtime/lambda_entry.py",
            "v22/runtime/lambda_adapter.py",
            "v22/core/live_sources.py",
            "v22/storage/database.py",
            "config/v22_live_assets.json",
        }
        missing = required - names
        if missing:
            raise SystemExit(f"missing Lambda package files: {sorted(missing)}")
        if any(n.startswith("v22/tests/") or "__pycache__" in n for n in names):
            raise SystemExit("test/cache files leaked into Lambda package")
        if require_deps and not any(n.startswith("psycopg/") for n in names):
            raise SystemExit("psycopg dependency missing from deployment ZIP")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="dist/v22-lambda.zip")
    ap.add_argument("--install-deps", action="store_true")
    args = ap.parse_args()
    path = build(ROOT / args.output, args.install_deps)
    inspect(path, args.install_deps)
    size = path.stat().st_size
    if size > 50 * 1024 * 1024:
        raise SystemExit(f"deployment ZIP exceeds direct-upload limit: {size} bytes")
    print(f"PASS lambda-package path={path} bytes={size} deps={args.install_deps}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
