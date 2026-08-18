from __future__ import annotations
import json
import os
from pathlib import Path
import sys

# GitHub Actions launches this file from /scripts. Put the repository root on
# sys.path before importing V22 so the runner works regardless of launcher cwd.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from v22.storage import Database
from v22.trading import PaperCompetitionEngine


def main() -> int:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise SystemExit("DATABASE_URL is required")
    db = Database(url)
    db.migrate()
    result = PaperCompetitionEngine(db).run_once()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
