from __future__ import annotations

import json
from pathlib import Path
import sys
import types
import uuid

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from v22 import __version__
from v22.contracts import CoverageContract
from v22.storage.database import Database


class Cursor:
    def __init__(self, row):
        self.row = row
        self.rowcount = 1
    def execute(self, sql, params=()):
        pass
    def fetchall(self):
        return [self.row]
    def fetchone(self):
        return self.row


class Connection:
    def __init__(self, row):
        self.row = row
    def cursor(self):
        return Cursor(self.row)
    def commit(self):
        pass
    def rollback(self):
        pass
    def close(self):
        pass


def main():
    native_uuid = uuid.uuid4()
    fake = types.ModuleType('psycopg')
    fake.connect = lambda dsn, row_factory=None: Connection({'cycle_id': native_uuid})
    rows = types.ModuleType('psycopg.rows')
    rows.dict_row = object()
    sys.modules['psycopg'] = fake
    sys.modules['psycopg.rows'] = rows

    db = Database('postgresql://u:p@ep-test-pooler.ap-southeast-2.aws.neon.tech/neondb')
    returned = db.query('SELECT cycle_id FROM brain_cycles')[0]['cycle_id']
    coverage = CoverageContract(cycle_id=returned, asset_id='BTC')
    assert isinstance(returned, str)
    assert returned == str(native_uuid)
    assert coverage.cycle_id == str(native_uuid)
    print(json.dumps({
        'status': 'passed',
        'version': __version__,
        'native_driver_type': 'uuid.UUID',
        'domain_type': type(returned).__name__,
        'contract_accepts_id': True,
    }, indent=2))


if __name__ == '__main__':
    main()
