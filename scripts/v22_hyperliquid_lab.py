from __future__ import annotations
import asyncio,os,signal,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from v22.hyperliquid_lab import HyperliquidLabConfig,HyperliquidLabService
async def main():
    url=os.getenv("DATABASE_URL","").strip()
    if not url:raise SystemExit("DATABASE_URL is required")
    svc=HyperliquidLabService(url,HyperliquidLabConfig.from_env())
    loop=asyncio.get_running_loop()
    for sig in (signal.SIGINT,signal.SIGTERM):
        try:loop.add_signal_handler(sig,svc.stop_event.set)
        except NotImplementedError:pass
    await svc.run()
if __name__=="__main__":asyncio.run(main())
