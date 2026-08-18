# V22.11 — Fresh Paper Brains & Bounded Learning

V22.11 restarts the paper-trading competition from clean state while retaining V22 market evidence.

Safety:
- Four isolated A$100,000 paper wallets.
- 1.5% initial probe.
- 1.0% confirmation add, maximum two adds.
- 6% maximum per asset.
- 30% maximum total deployment.
- 70% minimum cash reserve.
- Six open positions maximum.
- 5% hard paper stop.
- No averaging down.
- No live execution code path.
- Learning starts only after 8 closed trades.
- Learning may reduce sizing automatically; it can only restore toward baseline and can never exceed baseline.

The scheduled paper workflow runs five minutes after each 15-minute market observer.
