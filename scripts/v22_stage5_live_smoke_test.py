from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from v22.contracts import CycleType
from v22.core import DeterministicBrainCore, LiveAssetSpec, LiveEvidenceCollector
from v22.storage import BrainRepository, Database


class SyntheticBinance:
    def get_json(self,path,params):
        step={'1m':60_000,'5m':300_000,'15m':900_000}[params['interval']]
        end=int(params['endTime']); limit=int(params['limit']); start=end-limit*step
        rows=[]
        for i in range(limit):
            o=start+i*step; c=o+step-1; px=100+i*0.15; vol=1000+(i%5)*50
            rows.append([o,str(px),str(px+0.8),str(px-0.8),str(px+0.25),str(vol),c,'0',1,'0','0','0'])
        return rows


def run():
    at=datetime(2026,8,17,6,30,tzinfo=timezone.utc)
    with tempfile.TemporaryDirectory() as td:
        root=Path(td); db=Database(f"sqlite:///{root/'brain.db'}"); db.migrate(); repo=BrainRepository(db)
        specs=(LiveAssetSpec('ETH','ETHUSDT'),LiveAssetSpec('LINK','LINKUSDT'))
        collector=LiveEvidenceCollector(root,http_client=SyntheticBinance(),asset_specs=specs)
        market=DeterministicBrainCore(repo,collector).run(CycleType.MARKET_15M,at,workflow_id='stage5-smoke-market')
        micro=DeterministicBrainCore(repo,collector).run(CycleType.MICRO_5M,at,workflow_id='stage5-smoke-micro')
        assert market.status=='COMPLETED' and market.analysed_assets==2
        assert micro.status=='COMPLETED' and micro.analysed_assets==2
        result={'status':'passed','market_15m':market.__dict__,'micro_5m':micro.__dict__,'ai_calls':repo.db.scalar('SELECT COUNT(*) FROM ai_calls')}
        print(json.dumps(result,indent=2,default=str))

if __name__=='__main__': run()
