from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile
import types

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def load_observer():
    # The release test exercises pure observer logic without internet access.
    # Provide a minimal yfinance stub when the package is unavailable locally.
    if "yfinance" not in sys.modules:
        stub = types.ModuleType("yfinance")
        stub.download = lambda *args, **kwargs: pd.DataFrame()
        sys.modules["yfinance"] = stub
    path = ROOT / "scripts" / "observer_15m.py"
    spec = importlib.util.spec_from_file_location("observer_15m_release_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_page_navigation() -> None:
    text = (ROOT / "app.py").read_text(encoding="utf-8")
    # Support both the legacy single-file shell and the V22 platform bridge.
    radio_match = re.search(r'(?:st\.sidebar\.radio|st\.radio)\("Navigation",\s*\[(.*?)\],\s*label_visibility', text, re.S)
    if not radio_match:
        raise AssertionError("Navigation list was not found.")
    entries = re.findall(r'"([^"]+)"', radio_match.group(1))

    # Legacy app used `titles` + page_header; V22 uses `TITLES` and renders the
    # selected tuple directly. Both must provide a title for every navigation page.
    title_block = ""
    if "titles = {" in text and "page_header(*titles[selection])" in text:
        title_start = text.index("titles = {")
        title_end = text.index("page_header(*titles[selection])")
        title_block = text[title_start:title_end]
    elif "TITLES={" in text and "title,subtitle=TITLES[selection]" in text:
        title_start = text.index("TITLES={")
        title_end = text.index("title,subtitle=TITLES[selection]")
        title_block = text[title_start:title_end]
    else:
        raise AssertionError("Navigation title map was not found.")
    missing_titles = [entry for entry in entries if f'"{entry}":' not in title_block]
    if missing_titles:
        raise AssertionError(f"Missing page titles: {missing_titles}")

    handlers = set(re.findall(r'(?:if|elif) selection\s*==\s*"([^"]+)"', text))
    # Legacy Today page was sometimes the first plain `if`; V22 is included by the regex.
    if 'selection == "Today"' in text or 'selection=="Today"' in text:
        handlers.add("Today")
    if '\nelse:\n' in text and "Signal Lab" in entries:
        handlers.add("Signal Lab")
    missing_handlers = [entry for entry in entries if entry not in handlers]
    if missing_handlers:
        raise AssertionError(f"Missing page handlers: {missing_handlers}")


def test_json_serialisation(observer) -> None:
    payload = {
        "native": True,
        "numpy_bool": np.bool_(True),
        "numpy_int": np.int64(7),
        "numpy_float": np.float64(1.25),
        "array": np.array([1, 2, 3]),
        "timestamp": pd.Timestamp("2026-08-05T08:00:00Z"),
        "nested": {"flag": np.bool_(False)},
    }
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "test.json"
        observer.write_json(path, payload)
        loaded = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["numpy_bool"] is True
        assert loaded["nested"]["flag"] is False
        assert loaded["numpy_int"] == 7
        assert loaded["array"] == [1, 2, 3]


def synthetic_frame(direction: str) -> pd.DataFrame:
    index = pd.date_range("2026-07-30", periods=220, freq="15min", tz="UTC")
    if direction == "up":
        close = np.linspace(100, 125, len(index)) + np.sin(np.arange(len(index)) / 2.5) * 2.0
    else:
        close = np.linspace(125, 95, len(index)) + np.sin(np.arange(len(index)) / 2.5) * 2.0
    frame = pd.DataFrame(index=index)
    frame["Close"] = close
    frame["Open"] = frame["Close"].shift(1).fillna(frame["Close"])
    frame["High"] = frame[["Open", "Close"]].max(axis=1) + 0.2
    frame["Low"] = frame[["Open", "Close"]].min(axis=1) - 0.2
    frame["Volume"] = np.linspace(1000, 2600, len(index))
    return frame[["Open", "High", "Low", "Close", "Volume"]]


def test_observer_signal(observer) -> None:
    bullish = observer.observe(synthetic_frame("up"))
    bearish = observer.observe(synthetic_frame("down"))
    assert bullish is not None and bearish is not None
    json.dumps(observer.sanitise_json(bullish))
    json.dumps(observer.sanitise_json(bearish))
    assert isinstance(bullish["breakout"], bool)
    assert isinstance(bearish["breakdown"], bool)


def base_wallet() -> dict:
    return {
        "wallet_id": "TEST",
        "name": "Test wallet",
        "starting_cash": 100000.0,
        "cash": 100000.0,
        "equity": 100000.0,
        "realised_pnl": 0.0,
        "unrealised_pnl": 0.0,
        "max_positions": 8,
        "position_size_pct": 10.0,
        "minimum_cash_reserve_pct": 20.0,
        "fee_pct_per_side": 0.10,
        "slippage_pct_per_side": 0.05,
        "open_positions": [],
        "closed_positions": [],
        "rejected_opportunities": [],
        "equity_history": [],
        "activity_journal": [],
    }


def signal(symbol: str, call: str, price: float, return_1h: float = 1.0) -> dict:
    return {
        "symbol": symbol,
        "name": symbol,
        "narrative": "Test",
        "signal": call,
        "price": price,
        "return_1h": return_1h,
        "rvol": 1.8,
        "rsi": 60,
        "bullish_conditions": 9 if "BUY" in call else 1,
        "bearish_conditions": 9 if "SELL" in call else 1,
        "candle_time": "2026-08-05T08:00:00+00:00",
    }


def test_wallet_lifecycle(observer) -> None:
    wallet = base_wallet()
    wallet = observer.update_wallet(
        wallet, [signal("BTC", "EARLY BUY", 100.0)], "2026-08-05T08:00:00+00:00"
    )
    assert len(wallet["open_positions"]) == 1
    assert wallet["open_positions"][0]["direction"] == "LONG"

    wallet = observer.update_wallet(
        wallet, [signal("BTC", "EARLY BUY", 105.0)], "2026-08-05T08:15:00+00:00"
    )
    assert wallet["equity"] > 100000

    wallet = observer.update_wallet(
        wallet, [signal("BTC", "EARLY SELL", 104.0)], "2026-08-05T08:30:00+00:00"
    )
    assert wallet["closed_positions"][-1]["exit_reason"] == "Observer reversal"

    short_wallet = base_wallet()
    short_wallet = observer.update_wallet(
        short_wallet, [signal("SOL", "EARLY SELL", 100.0, -1.0)], "2026-08-05T09:00:00+00:00"
    )
    assert short_wallet["open_positions"][0]["direction"] == "SHORT"
    short_wallet = observer.update_wallet(
        short_wallet, [signal("SOL", "EARLY SELL", 95.0, -2.0)], "2026-08-05T09:15:00+00:00"
    )
    assert short_wallet["equity"] > 100000


def test_templates() -> None:
    contract = json.loads((ROOT / "config" / "persistent_data.json").read_text(encoding="utf-8"))
    for filename in contract["files"]:
        template = ROOT / "data" / "templates" / filename.replace(".json", ".template.json")
        if not template.exists():
            raise AssertionError(f"Missing template for {filename}")
        json.loads(template.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--observer-only", action="store_true")
    args = parser.parse_args()

    observer = load_observer()
    test_json_serialisation(observer)
    test_observer_signal(observer)
    test_wallet_lifecycle(observer)
    test_templates()
    if not args.observer_only:
        test_page_navigation()

    print(json.dumps({
        "status": "passed",
        "observer_only": args.observer_only,
        "tests": [
            "page navigation" if not args.observer_only else "observer startup",
            "NumPy/Pandas JSON serialisation",
            "synthetic bullish and bearish observer signals",
            "long entry and revaluation",
            "long reversal exit",
            "short entry and profitable revaluation",
            "protected runtime templates",
        ],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
