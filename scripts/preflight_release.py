from __future__ import annotations

from pathlib import Path
import ast
import json
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    required = [
        "app.py",
        "requirements.txt",
        "holdings.json",
        "config/external_sources.json",
        "config/persistent_data.json",
        "scripts/bootstrap_runtime.py",
        "scripts/hourly_runner.py",
        "scripts/external_intelligence.py",
        "scripts/signal_recorder.py",
        ".github/workflows/hourly_signal_recorder.yml",
        "V22_ARCHITECTURE.md",
        "README_V22_1.md",
        "release_manifest_v22.json",
        "v22/contracts/models.py",
        "v22/storage/repository.py",
        "v22/migrations/002_brain_memory_sqlite.sql",
        "v22/migrations/002_brain_memory_postgres.sql",
        "v22/tests/test_stage1_brain_memory.py",
        "scripts/v22_stage1_smoke_test.py",
        "README_V22_3.md",
        "v22/failure/engine.py",
        "v22/migrations/003_failure_engine_sqlite.sql",
        "v22/migrations/003_failure_engine_postgres.sql",
        "v22/tests/test_stage3_failure_engine.py",
        "scripts/v22_stage3_failure_smoke_test.py",
    ]

    missing = [name for name in required if not (ROOT / name).exists()]
    if missing:
        raise FileNotFoundError(f"Missing required files: {missing}")

    for path in ROOT.rglob("*.py"):
        if "__pycache__" not in path.parts:
            ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    json.loads((ROOT / "holdings.json").read_text(encoding="utf-8"))
    json.loads((ROOT / "config" / "external_sources.json").read_text(encoding="utf-8"))
    json.loads((ROOT / "release_manifest_v22.json").read_text(encoding="utf-8"))
    contract = json.loads((ROOT / "config" / "persistent_data.json").read_text(encoding="utf-8"))

    live_runtime_names = set(contract["files"])
    release_runtime_files = {
        path.name for path in (ROOT / "data").glob("*.json")
        if path.is_file()
    }
    unsafe = sorted(live_runtime_names & release_runtime_files)
    if unsafe:
        raise RuntimeError(
            "Release contains live runtime filenames and could overwrite records: "
            + ", ".join(unsafe)
        )

    print(json.dumps({
        "status": "passed",
        "required_files": len(required),
        "python_files_checked": len(list(ROOT.rglob("*.py"))),
        "persistent_files_protected": sorted(live_runtime_names),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
