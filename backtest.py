"""
Backtest for Second Wave Hunter - uses the exact same signal logic as scanner.py.

For every signal it simulates a trade:
  - Entry : open of the NEXT 15m candle after the signal candle
  - Stop  : below the correction low (minus STOP_BUFFER)
  - Target: 1R / 1.5R / 2R, or the first-wave high
  - Exit  : stop, target, or timeout (MAX_HOLD bars). If stop and target are
            both touched inside one candle, the STOP is assumed to hit first.
  - Costs : COST is deducted from every trade (fees + slippage, round trip)

Usage:
    python backtest.py
Environment variables (optional): DAYS, TOP_N, STOP_BUFFER, COST, MAX_HOLD
"""
import os
import time
from concurrent.futures import ThreadPoolExecutor

os.environ.setdefault("TOP_N", "50")

import numpy as np
import pandas as pd

import scanner

DAYS = int(os.getenv("DAYS", "90"))
WARMUP_DAYS = 10
STOP_BUFFER = float(os.getenv("STOP_BUFFER", "0.005"))   # 0.5% under correction low
COST = float(os.getenv("COST", "0.003"))                 # 0.3% round trip
MAX_HOLD = int(os.getenv("MAX_HOLD", "96"))              # 96 x 15m = 24h
MIN_RISK = 0.003                                         # skip trades with <0.3% risk

CONFIGS = [("Target 1R", 1.0), ("Target 1.5R", 1.5), ("Target 2R", 2.0),
           ("Target = wave high", None)]
DAY_MS = 86_400_000


# ------------------------------------------------------------------
# DATA
# ------------------------------------------------------------------
def klines_range(symbol, interval, start_ms, end_ms, closed_only=False):
    rows, cur = [], int(start_ms)
    while cur < end_ms:
        data = scanner.api("/api/v3/klines", {
            "symbol": symbol, "interval": interval,
            "startTime": cur, "endTime": int(end_ms), "limit": 1000})
        if not data:
            break
        rows += data
        cur = int(data[-1][6]) + 1
        if len(data) < 1000:
            break
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows).iloc[:, :7]
    df.columns = ["open_time", "open", "high", "low", "close", "volume", "close_time"]
    df = df.astype(float).drop_duplicates("open_time").reset_index(drop=True)
    if closed_only:
        df = df[df["close_time"] < time.time() * 1000].reset_index(drop=True)
    return df


def build(df, h1, h4):
    """Same features as scanner.prepare()."""
    h4 = h4.copy()
    h1 = h1.copy()
    h4["v_prev"] = h4["volume"].shift(1)
    h4["avg_prev"] = h4["volume"].rolling(20).mean().shift(1)
    h1["c_prev"] = h1["close"].shift(1)
    h1["ema_prev"] = h1["close"].ewm(span=50, adjust=False).mean().shift(1)

    df = pd.merge_asof(df, h4[["open_time", "v_prev", "avg_prev"]], on="open_time")
    df = pd.merge_asof(df, h1[["open_time", "c_prev", "ema_prev"]], on="open_time")

    d = df["close"].diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    df["rsi"] = (100 - 100 / (1 + up / dn.replace(0, np.nan))).fillna(100)
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
    df["vavg"] = df["volume"].rolling(20).mean()
    return df


# ------------------------------------------------------------------
# SIMULATION
# ------------------------------------------------------------------
def simulate(df, sigs, symbol, label, rr):
    o = df["open"].to_numpy(); h = df["high"].to_numpy()
    l = df["low"].to_numpy(); c = df["close"].to_numpy()
    idx = {int(t): i for i, t in enumerate(df["open_time"].to_numpy())}
    n = len(df)
    busy = -1
    out = []

    for s in sorted(sigs, key=lambda x: x["open_time"]):
        i = idx.get(s["open_time"])
        if i is None:
            continue
        e = i + 1
        if e >= n or e <= busy:
            continue

        entry = o[e]
        rng = s["wave_high"] - s["wave_low"]
        corr_low = s["wave_high"] - s["retrace"] / 100 * rng
        stop = corr_low * (1 - STOP_BUFFER)
        risk = (entry - stop) / entry
        if risk < MIN_RISK:
            continue

        target = entry + rr * (entry - stop) if rr else s["wave_high"]
        if target <= entry * (1 + COST + 0.002):
            continue

        last = min(n - 1, e + MAX_HOLD)
        exit_px, reason, j = None, "timeout", last
        for k in range(e, last + 1):
            if o[k] <= stop:
                exit_px, reason, j = o[k], "stop", k
                break
            if l[k] <= stop:
                exit_px, reason, j = stop, "stop", k
                break
            if h[k] >= target:
                exit_px, reason, j = target, "target", k
                break
        if exit_px is None:
            exit_px = c[last]
        busy = j

        ret = exit_px / entry - 1 - COST
        out.append({
            "symbol": symbol, "type": s["type"], "config": label,
            "signal_time": pd.to_datetime(s["open_time"], unit="ms").strftime("%Y-%m-%d %H:%M"),
            "entry": entry, "stop": stop, "target": target, "exit": exit_px,
            "reason": reason, "bars_held": j - e + 1,
            "risk_pct": round(risk * 100, 2),
            "net_return_pct": round(ret * 100, 2),
            "R": round(ret / risk, 3),
        })
    return out


def run_symbol(symbol):
    try:
        end = int(time.time() * 1000)
        start = end - (DAYS + WARMUP_DAYS) * DAY_MS
        df = klines_range(symbol, "15m", start, end, closed_only=True)
        if len(df) < 500:
            return symbol, [], []
        h1 = klines_range(symbol, "1h", start, end)
        h4 = klines_range(symbol, "4h", start, end)
        if h1.empty or h4.empty:
            return symbol, [], []
        df = build(df, h1, h4)

        scanner.MAX_AGE_BARS = 10 ** 9           # keep ALL historical signals
        cutoff = start + WARMUP_DAYS * DAY_MS
        sigs = [s for s in scanner.scan(df) if s["open_time"] >= cutoff]

        trades = []
        for label, rr in CONFIGS:
            trades += simulate(df, sigs, symbol, label, rr)
        return symbol, sigs, trades
    except Exception as e:
        print(f"[{symbol}] error: {e}")
        return symbol, [], []


# ------------------------------------------------------------------
# REPORT
# ------------------------------------------------------------------
def stats_line(tr):
    n = len(tr)
    if n == 0:
        return "no trades"
    r = np.array([t["R"] for t in tr])
    ret = np.array([t["net_return_pct"] for t in tr])
    wins = (r > 0).sum()
    gross_win = r[r > 0].sum()
    gross_loss = -r[r < 0].sum()
    pf = gross_win / gross_loss if gross_loss > 0 else float("inf")
    return (f"trades {n} | win {wins / n * 100:.0f}% | avg R {r.mean():+.2f} | "
            f"PF {pf:.2f} | avg net {ret.mean():+.2f}%")


def main():
    symbols = scanner.get_symbols()
    print(f"Backtest: {len(symbols)} symbols, last {DAYS} days, 15m")
    print(f"Costs {COST * 100:.2f}% round trip | stop buffer {STOP_BUFFER * 100:.2f}% | "
          f"max hold {MAX_HOLD} bars\n")

    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(run_symbol, symbols))

    all_sigs = [s for _, sg, _ in results for s in sg]
    all_trades = [t for _, _, tr in results for t in tr]

    weeks = DAYS / 7
    for kind in ("EARLY ENTRY", "CONFIRMED BUY"):
        k = sum(1 for s in all_sigs if s["type"] == kind)
        print(f"{kind}: {k} signals  (~{k / weeks:.1f} per week across all coins)")
    print()

    for kind in ("CONFIRMED BUY", "EARLY ENTRY"):
        print(f"=== {kind} ===")
        for label, _ in CONFIGS:
            tr = [t for t in all_trades if t["type"] == kind and t["config"] == label]
            print(f"{label:20s} {stats_line(tr)}")
        print()

    if all_trades:
        pd.DataFrame(all_trades).to_csv("trades.csv", index=False)
        print("Saved all trades to trades.csv")

    print("\nNotes:")
    print("- Only coins that are in today's top-volume list are tested (survivorship bias,")
    print("  results look better than reality).")
    print("- If stop and target are hit in the same candle, the stop is assumed first.")
    print("- Past results do not guarantee future results. This is not financial advice.")


if __name__ == "__main__":
    main()
