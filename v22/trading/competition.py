from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import urllib.request
import uuid
from typing import Any

from v22.storage import Database


DEFAULT_BRAINS = (
    ("Balanced Evidence", "BALANCED"),
    ("Trend Guardian", "TREND"),
    ("Breakout Scout", "BREAKOUT"),
    ("Flow Tracker", "FLOW"),
)


@dataclass(frozen=True)
class RiskPolicy:
    starting_cash_aud: float = 100_000.0
    probe_fraction: float = 0.015
    add_fraction: float = 0.010
    max_position_fraction: float = 0.060
    max_deployed_fraction: float = 0.300
    min_cash_reserve_fraction: float = 0.700
    max_open_positions: int = 6
    max_adds_per_position: int = 2
    stop_loss_fraction: float = 0.050
    min_trade_aud: float = 100.0
    learning_min_closed_trades: int = 8

    def __post_init__(self) -> None:
        if not (0 < self.probe_fraction <= self.max_position_fraction):
            raise ValueError("probe_fraction must be positive and <= max_position_fraction")
        if not (0 < self.add_fraction <= self.max_position_fraction):
            raise ValueError("add_fraction must be positive and <= max_position_fraction")
        if self.max_deployed_fraction + self.min_cash_reserve_fraction > 1.000001:
            raise ValueError("deployment and reserve limits overlap")
        if self.max_position_fraction > self.max_deployed_fraction:
            raise ValueError("single-position cap cannot exceed total deployment cap")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: datetime) -> str:
    return v.astimezone(timezone.utc).isoformat()


def _json(v: Any) -> str:
    return json.dumps(v, sort_keys=True, separators=(",", ":"))


class PaperCompetitionEngine:
    """Long-only deterministic paper competition over durable V22 evidence.

    Safety properties:
    - isolated fresh wallets with equal starting capital
    - small probes, capped scale-ins, no averaging down
    - >=70% reserve cash and <=30% total deployment
    - <=6% in any single asset
    - learning may reduce risk automatically, never raise above baseline 1.0
    - no live-execution path exists in this module
    """

    RESET_KEY = "V22_FRESH_PAPER_2026_08"

    def __init__(self, db: Database, policy: RiskPolicy | None = None):
        self.db = db
        self.policy = policy or RiskPolicy()

    @property
    def _ph(self) -> str:
        return "?" if self.db.kind == "sqlite" else "%s"

    def _sql(self, sqlite_sql: str, postgres_sql: str) -> str:
        return sqlite_sql if self.db.kind == "sqlite" else postgres_sql

    def _bool(self, v: bool):
        return 1 if self.db.kind == "sqlite" and v else v

    def _fx_aud_per_usd(self) -> float:
        try:
            req = urllib.request.Request(
                "https://api.frankfurter.dev/v2/rate/USD/AUD",
                headers={"User-Agent": "V22-Paper-Competition/1.0"},
            )
            with urllib.request.urlopen(req, timeout=4) as response:
                payload = json.loads(response.read().decode("utf-8"))
            rate = float(payload.get("rate") or 0)
            if rate > 0:
                return rate
        except Exception:
            pass
        return 1.4092

    def ensure_competition(self) -> dict:
        ph = self._ph
        row = self.db.query(f"SELECT * FROM paper_competitions WHERE reset_key={ph}", (self.RESET_KEY,))
        if row:
            comp = row[0]
        else:
            cid = str(uuid.uuid4())
            sql = self._sql(
                "INSERT INTO paper_competitions(competition_id,reset_key,name,currency,starting_cash_aud,status,created_at) VALUES (?,?,?,?,?,?,?)",
                "INSERT INTO paper_competitions(competition_id,reset_key,name,currency,starting_cash_aud,status,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            )
            self.db.execute(sql, (cid, self.RESET_KEY, "V22 Fresh Paper Competition", "AUD", self.policy.starting_cash_aud, "ACTIVE", _iso(_now())))
            comp = self.db.query(f"SELECT * FROM paper_competitions WHERE competition_id={ph}", (cid,))[0]
        for name, strategy in DEFAULT_BRAINS:
            exists = self.db.query(
                f"SELECT brain_id FROM paper_brains WHERE competition_id={ph} AND strategy_key={ph}",
                (comp["competition_id"], strategy),
            )
            if not exists:
                bid = str(uuid.uuid4())
                sql = self._sql(
                    "INSERT INTO paper_brains(brain_id,competition_id,name,strategy_key,cash_aud,realised_pnl_aud,risk_multiplier,trades_closed,wins,losses,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    "INSERT INTO paper_brains(brain_id,competition_id,name,strategy_key,cash_aud,realised_pnl_aud,risk_multiplier,trades_closed,wins,losses,created_at,updated_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                )
                now = _iso(_now())
                self.db.execute(sql, (bid, comp["competition_id"], name, strategy, self.policy.starting_cash_aud, 0.0, 1.0, 0, 0, 0, now, now))
        return comp

    def _latest_market_snapshot(self) -> tuple[dict | None, dict[str, dict[str, Any]], dict[str, float], dict[str, list[str]]]:
        ph = self._ph
        rows = self.db.query(
            "SELECT * FROM brain_cycles WHERE cycle_type='MARKET_15M' AND status='COMPLETED' ORDER BY completed_at DESC LIMIT 1"
        )
        if not rows:
            return None, {}, {}, {}
        cycle = rows[0]
        cid = cycle["cycle_id"]
        obs = self.db.query(
            f"SELECT observation_id,asset_id,metric,value_json,observed_at,quality FROM observation_records WHERE cycle_id={ph} ORDER BY asset_id,metric",
            (cid,),
        )
        evidence = self.db.query(
            f"SELECT evidence_id,asset_id,metric,value_json FROM evidence_records WHERE cycle_id={ph}",
            (cid,),
        )
        state: dict[str, dict[str, Any]] = {}
        evidence_ids: dict[str, list[str]] = {}
        prices: dict[str, float] = {}
        for r in obs:
            value = r["value_json"]
            if isinstance(value, str):
                try: value = json.loads(value)
                except Exception: pass
            state.setdefault(str(r["asset_id"]), {})[str(r["metric"])] = value
        for r in evidence:
            asset = str(r["asset_id"])
            evidence_ids.setdefault(asset, []).append(str(r["evidence_id"]))
            if str(r["metric"]) == "price_usd":
                value = r["value_json"]
                if isinstance(value, str):
                    try: value = json.loads(value)
                    except Exception: pass
                try: prices[asset] = float(value)
                except Exception: pass
        return cycle, state, prices, evidence_ids

    def _signal(self, strategy: str, state: dict[str, Any], has_position: bool) -> tuple[str, str]:
        trend = str(state.get("multi_timeframe_direction") or state.get("micro_trend_alignment") or "MIXED").upper()
        volume = str(state.get("volume_flow") or "FLAT").upper()
        participation = str(state.get("volume_participation") or "NORMAL").upper()
        structure = str(state.get("market_structure") or "RANGE").upper()

        exit_now = structure == "BREAKDOWN" or (trend == "DOWN" and volume == "DOWN")
        if has_position and exit_now:
            return "EXIT", f"adverse confirmation: trend={trend}, volume={volume}, structure={structure}"

        if strategy == "TREND":
            enter = trend == "UP" and volume != "DOWN"
            why = f"trend={trend}, volume={volume}"
        elif strategy == "BREAKOUT":
            enter = structure == "BREAKOUT" and volume == "UP"
            why = f"structure={structure}, volume={volume}"
        elif strategy == "FLOW":
            enter = volume == "UP" and participation in {"ELEVATED", "HIGH"} and trend != "DOWN"
            why = f"volume={volume}, participation={participation}, trend={trend}"
        else:
            score = sum([
                trend == "UP",
                volume == "UP",
                participation in {"ELEVATED", "HIGH"},
                structure == "BREAKOUT",
            ])
            enter = score >= 3
            why = f"evidence={score}/4; trend={trend}, volume={volume}, participation={participation}, structure={structure}"
        return ("ENTER" if enter else "HOLD"), why

    def _open_positions(self, brain_id: str) -> list[dict]:
        ph = self._ph
        return self.db.query(f"SELECT * FROM paper_positions WHERE brain_id={ph} AND status='OPEN' ORDER BY opened_at", (brain_id,))

    def _mark_prices(self, positions: list[dict], prices_aud: dict[str, float]) -> float:
        total = 0.0
        for p in positions:
            price = prices_aud.get(str(p["asset_id"]), float(p.get("last_price_aud") or p["avg_entry_price_aud"]))
            total += float(p["quantity"]) * price
        return total

    def _record_position_marks(self, cycle_id: str, positions: list[dict], prices_aud: dict[str, float]) -> None:
        now = _iso(_now())
        for p in positions:
            asset = str(p["asset_id"])
            price = prices_aud.get(asset)
            if not price or price <= 0:
                continue
            entry = float(p["avg_entry_price_aud"])
            ret = ((price / entry) - 1.0) * 100.0
            sql = self._sql(
                "INSERT OR IGNORE INTO paper_position_marks(mark_id,position_id,brain_id,cycle_id,asset_id,price_aud,return_pct,marked_at) VALUES (?,?,?,?,?,?,?,?)",
                "INSERT INTO paper_position_marks(mark_id,position_id,brain_id,cycle_id,asset_id,price_aud,return_pct,marked_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(position_id,cycle_id) DO NOTHING",
            )
            self.db.execute(sql, (str(uuid.uuid4()), p["position_id"], p["brain_id"], cycle_id, asset, price, ret, now))
            upd = self._sql(
                "UPDATE paper_positions SET last_price_aud=?,updated_at=? WHERE position_id=?",
                "UPDATE paper_positions SET last_price_aud=%s,updated_at=%s WHERE position_id=%s",
            )
            self.db.execute(upd, (price, now, p["position_id"]))

    def _record_trade_outcome(self, brain: dict, position: dict, exit_price: float, proceeds: float,
                              pnl: float, ret: float, exit_reason: str, closed_at: str) -> None:
        ph = self._ph
        marks = self.db.query(
            f"SELECT return_pct FROM paper_position_marks WHERE position_id={ph} ORDER BY marked_at",
            (position["position_id"],),
        )
        excursions = [float(m["return_pct"]) for m in marks]
        excursions.append(((exit_price / float(position["avg_entry_price_aud"])) - 1.0) * 100.0)
        mfe = max(excursions) if excursions else ret
        mae = min(excursions) if excursions else ret
        decision = self.db.query(
            f"SELECT reason,evidence_json FROM paper_trade_decisions "
            f"WHERE brain_id={ph} AND asset_id={ph} AND action='ENTER' AND observed_at <= {ph} "
            f"ORDER BY observed_at DESC LIMIT 1",
            (brain["brain_id"], position["asset_id"], position["opened_at"]),
        )
        entry_reason = decision[0]["reason"] if decision else None
        entry_evidence = decision[0]["evidence_json"] if decision else "{}"
        if not isinstance(entry_evidence, str):
            entry_evidence = _json(entry_evidence)
        opened = datetime.fromisoformat(str(position["opened_at"]).replace("Z", "+00:00"))
        closed = datetime.fromisoformat(str(closed_at).replace("Z", "+00:00"))
        holding_minutes = max(0.0, (closed - opened).total_seconds() / 60.0)
        sql = self._sql(
            "INSERT OR IGNORE INTO paper_trade_outcomes(outcome_id,position_id,brain_id,asset_id,entry_price_aud,exit_price_aud,cost_basis_aud,proceeds_aud,pnl_aud,return_pct,max_favourable_pct,max_adverse_pct,holding_minutes,entry_reason,exit_reason,entry_evidence_json,opened_at,closed_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            "INSERT INTO paper_trade_outcomes(outcome_id,position_id,brain_id,asset_id,entry_price_aud,exit_price_aud,cost_basis_aud,proceeds_aud,pnl_aud,return_pct,max_favourable_pct,max_adverse_pct,holding_minutes,entry_reason,exit_reason,entry_evidence_json,opened_at,closed_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s) ON CONFLICT(position_id) DO NOTHING",
        )
        self.db.execute(sql, (str(uuid.uuid4()), position["position_id"], brain["brain_id"], position["asset_id"],
                             float(position["avg_entry_price_aud"]), exit_price, float(position["cost_basis_aud"]),
                             proceeds, pnl, ret, mfe, mae, holding_minutes, entry_reason, exit_reason,
                             entry_evidence, position["opened_at"], closed_at))

    def _decision(self, brain: dict, cycle_id: str, asset: str, action: str, reason: str,
                  approved: bool, requested: float, approved_notional: float,
                  price_aud: float, fx: float, evidence: dict[str, Any]) -> bool:
        sql = self._sql(
            "INSERT OR IGNORE INTO paper_trade_decisions(decision_id,brain_id,cycle_id,asset_id,action,reason,risk_approved,requested_notional_aud,approved_notional_aud,price_aud,fx_aud_per_usd,observed_at,evidence_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            "INSERT INTO paper_trade_decisions(decision_id,brain_id,cycle_id,asset_id,action,reason,risk_approved,requested_notional_aud,approved_notional_aud,price_aud,fx_aud_per_usd,observed_at,evidence_json) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb) ON CONFLICT(brain_id,cycle_id,asset_id,action) DO NOTHING",
        )
        try:
            inserted = self.db.execute(sql, (str(uuid.uuid4()), brain["brain_id"], cycle_id, asset, action, reason,
                                  self._bool(approved), requested, approved_notional, price_aud, fx, _iso(_now()), _json(evidence)))
            return inserted > 0
        except Exception as exc:
            # Composite uniqueness makes workflow retries idempotent. SQLite and
            # Postgres report the duplicate differently, so confirm existence
            # rather than attempting any paper execution after a duplicate.
            ph = self._ph
            existing = self.db.query(
                f"SELECT decision_id FROM paper_trade_decisions WHERE brain_id={ph} AND cycle_id={ph} AND asset_id={ph} AND action={ph}",
                (brain["brain_id"], cycle_id, asset, action),
            )
            if existing:
                return False
            raise exc

    def _buy(self, brain: dict, cycle_id: str, asset: str, price: float, notional: float, reason: str, position: dict | None) -> None:
        qty = notional / price
        now = _iso(_now())
        if position is None:
            pid = str(uuid.uuid4())
            sql = self._sql(
                "INSERT INTO paper_positions(position_id,brain_id,asset_id,quantity,avg_entry_price_aud,cost_basis_aud,opened_at,updated_at,status,add_count,last_price_aud) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                "INSERT INTO paper_positions(position_id,brain_id,asset_id,quantity,avg_entry_price_aud,cost_basis_aud,opened_at,updated_at,status,add_count,last_price_aud) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            )
            self.db.execute(sql, (pid, brain["brain_id"], asset, qty, price, notional, now, now, "OPEN", 0, price))
        else:
            pid = position["position_id"]
            old_qty = float(position["quantity"])
            old_cost = float(position["cost_basis_aud"])
            new_qty = old_qty + qty
            new_cost = old_cost + notional
            avg = new_cost / new_qty
            sql = self._sql(
                "UPDATE paper_positions SET quantity=?,avg_entry_price_aud=?,cost_basis_aud=?,updated_at=?,add_count=add_count+1,last_price_aud=? WHERE position_id=?",
                "UPDATE paper_positions SET quantity=%s,avg_entry_price_aud=%s,cost_basis_aud=%s,updated_at=%s,add_count=add_count+1,last_price_aud=%s WHERE position_id=%s",
            )
            self.db.execute(sql, (new_qty, avg, new_cost, now, price, pid))
        cash_after = float(brain["cash_aud"]) - notional
        upd = self._sql(
            "UPDATE paper_brains SET cash_aud=?,updated_at=? WHERE brain_id=?",
            "UPDATE paper_brains SET cash_aud=%s,updated_at=%s WHERE brain_id=%s",
        )
        self.db.execute(upd, (cash_after, now, brain["brain_id"]))
        trade = self._sql(
            "INSERT INTO paper_trades(trade_id,brain_id,position_id,cycle_id,asset_id,side,quantity,price_aud,notional_aud,executed_at,reason,cash_after_aud) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            "INSERT INTO paper_trades(trade_id,brain_id,position_id,cycle_id,asset_id,side,quantity,price_aud,notional_aud,executed_at,reason,cash_after_aud) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        )
        self.db.execute(trade, (str(uuid.uuid4()), brain["brain_id"], pid, cycle_id, asset, "BUY", qty, price, notional, now, reason, cash_after))

    def _sell(self, brain: dict, cycle_id: str, position: dict, price: float, reason: str) -> None:
        qty = float(position["quantity"])
        proceeds = qty * price
        cost = float(position["cost_basis_aud"])
        pnl = proceeds - cost
        ret = (pnl / cost * 100.0) if cost else 0.0
        cash_after = float(brain["cash_aud"]) + proceeds
        now = _iso(_now())
        updpos = self._sql(
            "UPDATE paper_positions SET status='CLOSED',closed_at=?,updated_at=?,last_price_aud=? WHERE position_id=?",
            "UPDATE paper_positions SET status='CLOSED',closed_at=%s,updated_at=%s,last_price_aud=%s WHERE position_id=%s",
        )
        self.db.execute(updpos, (now, now, price, position["position_id"]))
        win = pnl > 0
        updbrain = self._sql(
            "UPDATE paper_brains SET cash_aud=?,realised_pnl_aud=realised_pnl_aud+?,trades_closed=trades_closed+1,wins=wins+?,losses=losses+?,updated_at=? WHERE brain_id=?",
            "UPDATE paper_brains SET cash_aud=%s,realised_pnl_aud=realised_pnl_aud+%s,trades_closed=trades_closed+1,wins=wins+%s,losses=losses+%s,updated_at=%s WHERE brain_id=%s",
        )
        self.db.execute(updbrain, (cash_after, pnl, 1 if win else 0, 0 if win else 1, now, brain["brain_id"]))
        trade = self._sql(
            "INSERT INTO paper_trades(trade_id,brain_id,position_id,cycle_id,asset_id,side,quantity,price_aud,notional_aud,executed_at,reason,cash_after_aud) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            "INSERT INTO paper_trades(trade_id,brain_id,position_id,cycle_id,asset_id,side,quantity,price_aud,notional_aud,executed_at,reason,cash_after_aud) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        )
        self.db.execute(trade, (str(uuid.uuid4()), brain["brain_id"], position["position_id"], cycle_id, position["asset_id"], "SELL", qty, price, proceeds, now, f"{reason}; return={ret:.3f}%", cash_after))
        self._record_trade_outcome(brain, position, price, proceeds, pnl, ret, reason, now)
        self._learn(brain["brain_id"])

    def _learn(self, brain_id: str) -> None:
        ph = self._ph
        brain = self.db.query(f"SELECT * FROM paper_brains WHERE brain_id={ph}", (brain_id,))[0]
        sample = int(brain["trades_closed"])
        if sample < self.policy.learning_min_closed_trades:
            return
        outcomes = self.db.query(
            f"SELECT return_pct,max_favourable_pct,max_adverse_pct FROM paper_trade_outcomes WHERE brain_id={ph} ORDER BY closed_at DESC LIMIT 50",
            (brain_id,),
        )
        returns = [float(o["return_pct"]) for o in outcomes]
        if not returns:
            return
        avg = sum(returns) / len(returns)
        win_rate = float(brain["wins"]) / max(1, sample)
        current = float(brain["risk_multiplier"])
        proposed = current
        reason = "performance inside neutral learning band"
        if win_rate < 0.45 or avg < 0:
            proposed = max(0.50, round(current - 0.05, 2))
            reason = "weak measured outcomes reduce future sizing"
        elif win_rate >= 0.60 and avg > 1.0 and current < 1.0:
            proposed = min(1.0, round(current + 0.05, 2))
            reason = "improved measured outcomes restore sizing toward baseline only"
        lesson_key = f"{sample}:{brain['wins']}:{brain['losses']}:{proposed:.2f}"
        sql = self._sql(
            "INSERT OR IGNORE INTO paper_lessons(lesson_id,brain_id,lesson_key,sample_size,wins,losses,win_rate,avg_return_pct,proposed_risk_multiplier,previous_risk_multiplier,state,reason,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            "INSERT INTO paper_lessons(lesson_id,brain_id,lesson_key,sample_size,wins,losses,win_rate,avg_return_pct,proposed_risk_multiplier,previous_risk_multiplier,state,reason,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(brain_id,lesson_key) DO NOTHING",
        )
        state = "PROMOTED" if proposed != current else "CANDIDATE"
        self.db.execute(sql, (str(uuid.uuid4()), brain_id, lesson_key, sample, int(brain["wins"]), int(brain["losses"]),
                              win_rate, avg, proposed, current, state, reason, _iso(_now())))
        if proposed != current:
            upd = self._sql(
                "UPDATE paper_brains SET risk_multiplier=?,updated_at=? WHERE brain_id=?",
                "UPDATE paper_brains SET risk_multiplier=%s,updated_at=%s WHERE brain_id=%s",
            )
            self.db.execute(upd, (proposed, _iso(_now()), brain_id))

    def run_once(self) -> dict[str, Any]:
        comp = self.ensure_competition()
        cycle, states, prices_usd, evidence_ids = self._latest_market_snapshot()
        if cycle is None:
            return {"status": "WAITING", "reason": "no completed MARKET_15M cycle"}
        fx = self._fx_aud_per_usd()
        prices = {a: p * fx for a, p in prices_usd.items() if p > 0}
        brains = self.db.query(f"SELECT * FROM paper_brains WHERE competition_id={self._ph} ORDER BY name", (comp["competition_id"],))
        executed = 0
        decisions = 0
        for raw_brain in brains:
            brain = dict(raw_brain)
            positions = self._open_positions(brain["brain_id"])
            self._record_position_marks(str(cycle["cycle_id"]), positions, prices)
            positions = self._open_positions(brain["brain_id"])
            by_asset = {str(p["asset_id"]): p for p in positions}
            deployed = self._mark_prices(positions, prices)
            starting = float(comp["starting_cash_aud"])
            reserve_floor = starting * self.policy.min_cash_reserve_fraction
            max_deployed = starting * self.policy.max_deployed_fraction
            risk_multiplier = min(1.0, max(0.5, float(brain["risk_multiplier"])))
            for asset in sorted(set(states) & set(prices)):
                state = states[asset]
                price = prices[asset]
                pos = by_asset.get(asset)
                action, reason = self._signal(str(brain["strategy_key"]), state, pos is not None)
                if pos is not None and price <= float(pos["avg_entry_price_aud"]) * (1.0 - self.policy.stop_loss_fraction):
                    action, reason = "EXIT", f"hard paper stop {self.policy.stop_loss_fraction*100:.1f}%"
                if action == "EXIT" and pos is not None:
                    fresh = self._decision(brain, str(cycle["cycle_id"]), asset, action, reason, True,
                                   float(pos["quantity"])*price, float(pos["quantity"])*price, price, fx,
                                   {"observations": state, "evidence_ids": evidence_ids.get(asset, [])})
                    if fresh:
                        self._sell(brain, str(cycle["cycle_id"]), pos, price, reason)
                        executed += 1; decisions += 1
                    brain = self.db.query(f"SELECT * FROM paper_brains WHERE brain_id={self._ph}", (brain["brain_id"],))[0]
                    continue
                if action != "ENTER":
                    continue

                # A winning position may be scaled; never average down.
                is_add = pos is not None
                if is_add:
                    if int(pos["add_count"]) >= self.policy.max_adds_per_position:
                        continue
                    if price <= float(pos["avg_entry_price_aud"]) * 1.005:
                        continue
                    fraction = self.policy.add_fraction
                else:
                    if len(positions) >= self.policy.max_open_positions:
                        continue
                    fraction = self.policy.probe_fraction

                requested = starting * fraction * risk_multiplier
                position_value = float(pos["quantity"])*price if pos else 0.0
                position_headroom = starting*self.policy.max_position_fraction - position_value
                deployment_headroom = max_deployed - deployed
                cash_headroom = float(brain["cash_aud"]) - reserve_floor
                approved_notional = max(0.0, min(requested, position_headroom, deployment_headroom, cash_headroom))
                approved = approved_notional >= self.policy.min_trade_aud
                fresh = self._decision(brain, str(cycle["cycle_id"]), asset, "ADD" if is_add else "ENTER", reason, approved,
                               requested, approved_notional if approved else 0.0, price, fx,
                               {"observations": state, "evidence_ids": evidence_ids.get(asset, []),
                                "risk_multiplier": risk_multiplier, "reserve_floor_aud": reserve_floor,
                                "max_deployed_aud": max_deployed})
                if fresh:
                    decisions += 1
                if approved and fresh:
                    self._buy(brain, str(cycle["cycle_id"]), asset, price, approved_notional, reason, pos)
                    executed += 1
                    brain = self.db.query(f"SELECT * FROM paper_brains WHERE brain_id={self._ph}", (brain["brain_id"],))[0]
                    positions = self._open_positions(brain["brain_id"])
                    by_asset = {str(p["asset_id"]): p for p in positions}
                    deployed = self._mark_prices(positions, prices)
        return {
            "status": "COMPLETED",
            "competition_id": str(comp["competition_id"]),
            "cycle_id": str(cycle["cycle_id"]),
            "brains": len(brains),
            "assets": len(states),
            "decisions_recorded": decisions,
            "trades_executed": executed,
            "fx_aud_per_usd": fx,
        }
