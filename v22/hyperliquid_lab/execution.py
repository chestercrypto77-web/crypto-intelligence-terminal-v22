from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class ExecutionReadiness:
    mode:str
    configured:bool
    reason:str

class HyperliquidTestnetExecutor:
    """Execution boundary for the lab. V22.15 ships DISABLED by default.
    The adapter is intentionally separate from signal generation so live market
    observation can be proven before testnet credentials are introduced.
    """
    def __init__(self,config):
        self.config=config
    def readiness(self):
        if self.config.execution_mode!="TESTNET":
            return ExecutionReadiness(self.config.execution_mode,False,"Execution disabled; observation laboratory only")
        return ExecutionReadiness("TESTNET",False,"Testnet signing configuration has not been supplied yet")
    def submit(self,*args,**kwargs):
        raise RuntimeError("V22.15 execution gate is closed")
