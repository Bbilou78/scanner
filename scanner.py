"""
Second Wave Hunter v2.6 - Python port + Telegram alerts
Scans Binance USDT pairs on the 15m timeframe and sends a Telegram message
when EARLY ENTRY or CONFIRMED BUY fires on a freshly closed candle.

Usage:
    python scanner.py          # normal scan
    python scanner.py test     # send a test Telegram message
"""
import json
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import requests

# ------------------------------------------------------------------
# SETTINGS (same defaults as the Pine Script inputs)
# ------------------------------------------------------------------
MIN_PUMP = 25.0          # Minimum First Wave %
MIN_RETRACE = 30.0       # Minimum Correction %
MAX_RETRACE = 70.0       # Maximum Correction %
DEEP_LEVEL = 60.0        # Deep Correction Level %
PIVOT_LEN = 4
BREAKOUT_LEN = 10
MAX_SETUP_BARS = 160
VOL15_MULT = 1.2
VOL4H_MULT = 1.3
CONFIRM_BARS = 3
USE_EMA200 = True
MIN_WAVE_BARS = 4

# ------------------------------------------------------------------
# BOT SETTINGS (environment variables)
# ------------------------------------------------------------------
TOP_N = int(os.getenv("TOP_N", "100"))          # how many USDT pairs to scan (by 24h volume)
SYMBOLS = os.getenv("SYMBOLS", "").strip()      # e.g. "BTCUSDT,ETHUSDT" to override TOP_N
MAX_AGE_BARS = int(os.getenv("MAX_AGE_BARS", "2"))  # accept signals up to N closed bars old
TZ_OFFSET_HOURS = int(os.getenv("TZ_OFFSET_HOURS", "1"))  # Algeria = UTC+1
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
STATE_FILE = "sent.json"

BASES = ["https://data-api.binance.vision", "https://api.binance.com"]
STABLES = {"USDC", "FDUSD", "TUSD", "USDP", "DAI", "EUR", "AEUR", "USDE", "XUSD", "BFUSD"}


# ------------------------------------------------------------------
# DATA
# ------------------------------------------------------------------
def api(path, params):
    last = None
    for base in BASES:
        try:
            r = requests.get(base + path, params=params, timeout=15)
            if r.status_code == 200:
                return r.json()
            last = f"{base} -> HTTP {r.status_code}"
        except requests.RequestException as e:
            last = f"{base} -> {e}"
    raise RuntimeError(last)


def klines(symbol, interval, limit, closed_only=True):
    data = api("/api/v3/klines", {"symbol": symbol, "interval": interval, "limit": limit})
    df = pd.DataFrame(data).iloc[:, :7]
    df.columns = ["open_time", "open", "high", "low", "close", "volume", "close_time"]
    df = df.astype(float)
    if closed_only:
        df = df[df["close_time"] < time.time() * 1000].reset_index(drop=True)
    return df


def get_symbols():
    if SYMBOLS:
        return [s.strip().upper() for s in SYMBOLS.split(",") if s.strip()]
    tickers = api("/api/v3/ticker/24hr", {})
    rows = []
    for t in tickers:
        s = t["symbol"]
        if not s.endswith("USDT"):
            continue
        base = s[:-4]
        if base in STABLES or base.endswith(("UP", "DOWN", "BULL", "BEAR")):
            continue
        rows.append((float(t["quoteVolume"]), s))
    rows.sort(reverse=True)
    return [s for _, s in rows[:TOP_N]]


# ------------------------------------------------------------------
# INDICATOR LOGIC
# ------------------------------------------------------------------
def prepare(symbol):
    df = klines(symbol, "15m", 1000)
    h1 = klines(symbol, "1h", 500, closed_only=False)
    h4 = klines(symbol, "4h", 100, closed_only=False)
    if len(df) < 250:
        return None

    # Higher timeframe values = previous completed HTF bar (like [1] + lookahead_on)
    h4["v_prev"] = h4["volume"].shift(1)
    h4["avg_prev"] = h4["volume"].rolling(20).mean().shift(1)
    h1["c_prev"] = h1["close"].shift(1)
    h1["ema_prev"] = h1["close"].ewm(span=50, adjust=False).mean().shift(1)

    df = pd.merge_asof(df, h4[["open_time", "v_prev", "avg_prev"]], on="open_time")
    df = pd.merge_asof(df, h1[["open_time", "c_prev", "ema_prev"]], on="open_time")

    d = df["close"].diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    df["rsi"] = 100 - 100 / (1 + up / dn.replace(0, np.nan))
    df["rsi"] = df["rsi"].fillna(100)
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema200"] = df["close"].ewm(span=200, adjust=False).mean()
    df["vavg"] = df["volume"].rolling(20).mean()
    return df


def reversal_series(df):
    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    o1, c1 = np.roll(o, 1), np.roll(c, 1)
    body = np.abs(c - o)
    lower = np.minimum(o, c) - l
    upper = h - np.maximum(o, c)
    engulf = (c > o) & (c1 < o1) & (c >= o1) & (o <= c1)
    hammer = (c > o) & (lower >= body * 2) & (upper <= body)
    piercing = (c1 < o1) & (c > o) & (c > (o1 + c1) / 2) & (o < c1)
    rev = engulf | hammer | piercing
    rev[0] = False
    return rev


def scan(df):
    n = len(df)
    P = PIVOT_LEN
    o = df["open"].to_numpy(); h = df["high"].to_numpy()
    l = df["low"].to_numpy(); c = df["close"].to_numpy()
    v = df["volume"].to_numpy(); vavg = df["vavg"].to_numpy()
    rsi = df["rsi"].to_numpy(); ema20 = df["ema20"].to_numpy(); ema200 = df["ema200"].to_numpy()
    v4 = df["v_prev"].to_numpy(); a4 = df["avg_prev"].to_numpy()
    c1h = df["c_prev"].to_numpy(); e1h = df["ema_prev"].to_numpy()
    open_time = df["open_time"].to_numpy()
    rev = reversal_series(df)

    low_p, low_b = [], []
    last_used = None
    wave_low = wave_high = corr_low = float("nan")
    wave_start = None
    active = invalid = rev_seen = False
    early_fired = conf_fired = False
    breakout_bar = None
    signals = []

    for i in range(n):
        # --- pivots (confirmed P bars later) ---
        pl = ph = None
        if i >= 2 * P:
            if l[i - P] == l[i - 2 * P:i + 1].min():
                pl = l[i - P]
            if h[i - P] == h[i - 2 * P:i + 1].max():
                ph = h[i - P]
        if pl is not None:
            low_p.append(pl)
            low_b.append(i - P)
        ph_bar = i - P

        # --- new first wave ---
        if ph is not None and low_b:
            sel = None
            for j in range(len(low_b) - 1, -1, -1):
                cb, cp = low_b[j], low_p[j]
                if (ph_bar - cb >= MIN_WAVE_BARS
                        and (last_used is None or cb > last_used)
                        and ph >= cp * (1 + MIN_PUMP / 100)):
                    sel = (cp, cb)
                    break
            if sel is not None:
                wave_low, wave_high = sel[0], ph
                corr_low = l[max(0, i - P):i + 1].min()
                wave_start = ph_bar
                active, invalid, rev_seen = True, False, False
                early_fired = conf_fired = False
                breakout_bar = None
                last_used = sel[1]

        # --- correction tracking ---
        if active and wave_start is not None:
            if i > wave_start:
                corr_low = min(corr_low, l[i])
            invalid = corr_low <= wave_low

        rng = wave_high - wave_low
        pct = (wave_high - corr_low) / rng * 100 if (rng == rng and rng > 0) else float("nan")
        pct_ok = pct == pct

        too_deep = active and pct_ok and pct > MAX_RETRACE
        expired = active and wave_start is not None and i - wave_start > MAX_SETUP_BARS
        if expired or invalid or too_deep:
            active = False
            breakout_bar = None
            rev_seen = False

        corr_ready = (active and not invalid and not too_deep and pct_ok
                      and MIN_RETRACE <= pct <= MAX_RETRACE)
        deep = corr_ready and pct >= DEEP_LEVEL

        # --- reversal confirmation ---
        if active and corr_ready and rev[i]:
            rev_seen = True
        conf_ready = corr_ready and (not deep or rev_seen)

        # --- local breakout ---
        res = h[i - BREAKOUT_LEN:i].max() if i >= BREAKOUT_LEN else float("nan")
        raw_breakout = res == res and c[i] > res
        if raw_breakout and conf_ready:
            breakout_bar = i
        fresh = (active and corr_ready and breakout_bar is not None
                 and i - breakout_bar <= CONFIRM_BARS)

        # --- entries ---
        vol15_ok = v[i] > vavg[i] * VOL15_MULT
        momentum_ok = c[i] > ema20[i] and rsi[i] >= 48
        core = fresh and vol15_ok and momentum_ok

        vol4h_ok = v4[i] > a4[i] * VOL4H_MULT
        trend1h_ok = c1h[i] > e1h[i]
        ema_ok = (not USE_EMA200) or c[i] > ema200[i]
        score = int(bool(vol4h_ok)) + int(bool(trend1h_ok)) + int(bool(ema_ok))

        early = core and not early_fired
        confirmed = core and score >= 2 and not conf_fired
        if early:
            early_fired = True
        if confirmed:
            conf_fired = True

        if (early or confirmed) and i >= n - MAX_AGE_BARS:
            signals.append({
                "type": "CONFIRMED BUY" if confirmed else "EARLY ENTRY",
                "open_time": int(open_time[i]),
                "price": float(c[i]),
                "score": score,
                "vol4h": bool(vol4h_ok), "trend1h": bool(trend1h_ok), "ema200": bool(ema_ok),
                "wave_low": float(wave_low), "wave_high": float(wave_high),
                "retrace": float(pct),
            })
    return signals


# ------------------------------------------------------------------
# TELEGRAM + STATE
# ------------------------------------------------------------------
def send_telegram(text):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[!] TELEGRAM_TOKEN / TELEGRAM_CHAT_ID not set. Message:\n" + text)
        return
    r = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={"chat_id": TELEGRAM_CHAT_ID, "text": text, "disable_web_page_preview": True},
        timeout=15,
    )
    if r.status_code != 200:
        print("Telegram error:", r.text)


def format_msg(symbol, s):
    icon = "🟢" if s["type"] == "CONFIRMED BUY" else "🟠"
    close_dt = datetime.fromtimestamp(s["open_time"] / 1000 + 900, tz=timezone.utc) \
        + timedelta(hours=TZ_OFFSET_HOURS - 0)
    mark = lambda ok: "✅" if ok else "❌"
    return (
        f"{icon} {s['type']}\n"
        f"{symbol}  (15m)\n"
        f"Price: {s['price']:.8g}\n"
        f"Wave: {s['wave_low']:.8g} -> {s['wave_high']:.8g}\n"
        f"Correction: {s['retrace']:.1f}%\n"
        f"Filters {s['score']}/3: 4H vol {mark(s['vol4h'])}  1H trend {mark(s['trend1h'])}  EMA200 {mark(s['ema200'])}\n"
        f"Candle close: {close_dt:%Y-%m-%d %H:%M}\n"
        f"https://www.tradingview.com/chart/?symbol=BINANCE:{symbol}"
    )


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state):
    cutoff = (time.time() - 3 * 86400) * 1000
    state = {k: v for k, v in state.items() if v > cutoff}
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=0)


# ------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------
def process(symbol):
    try:
        df = prepare(symbol)
        if df is None:
            return symbol, []
        return symbol, scan(df)
    except Exception as e:  # keep scanning other symbols
        print(f"[{symbol}] error: {e}")
        return symbol, []


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        send_telegram("✅ Second Wave Scanner: test message works.")
        return

    symbols = get_symbols()
    print(f"Scanning {len(symbols)} symbols...")
    state = load_state()

    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(process, symbols))

    sent = 0
    for symbol, sigs in results:
        for s in sigs:
            key = f"{symbol}|{s['open_time']}|{s['type']}"
            if key in state:
                continue
            send_telegram(format_msg(symbol, s))
            state[key] = s["open_time"]
            sent += 1
            print("ALERT:", key)
    save_state(state)
    print(f"Done. {sent} new alert(s).")


if __name__ == "__main__":
    main()
