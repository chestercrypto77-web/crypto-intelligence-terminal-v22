from __future__ import annotations
import asyncio, os, signal, sys
from pathlib import Path

REPO_ROOT=Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:sys.path.insert(0,str(REPO_ROOT))

from v22.realtime import RealtimeConfig, RealtimeObserverService

async def main() -> int:
    url=os.getenv("DATABASE_URL","").strip()
    if not url:raise SystemExit("DATABASE_URL is required")
    service=RealtimeObserverService(url,RealtimeConfig.from_env())
    loop=asyncio.get_running_loop()
    for sig in (signal.SIGTERM,signal.SIGINT):
        try:loop.add_signal_handler(sig,service.stop_event.set)
        except NotImplementedError:pass
    await service.run();return 0

if __name__=="__main__":raise SystemExit(asyncio.run(main()))
