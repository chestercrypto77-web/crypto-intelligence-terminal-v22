from __future__ import annotations
import json
import os

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
