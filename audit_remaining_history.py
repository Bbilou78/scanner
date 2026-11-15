import pickle
import requests
import pandas as pd
import numpy as np

data = pickle.load(open("BARDUSDT_snapshot.pkl", "rb"))

def fetch_history(interval, cutoff, target=1000):
    url = "https://api.binance.com/api/v3/klines"
    rows_all = []
    end_time = int(cutoff.timestamp() * 1000)

    while len(rows_all) < target:
        response = requests.get(
            url,
            params={
                "symbol": "BARDUSDT",
                "interval": interval,
                "limit": min(1000, target - len(rows_all)),
                "endTime": end_time
            },
            timeout=30
        )
        response.raise_for_status()
        rows = response.json()

        if not rows:
            break

        rows_all = rows + rows_all
        end_time = int(rows[0][0]) - 1

        if len(rows) < 1000:
            break

    df = pd.DataFrame(rows_all, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_base", "taker_quote", "ignore"
    ])

    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df["close"] = df["close"].astype(float)
    df = df.set_index("open_time").sort_index()

    now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    df = df[pd.to_datetime(df["close_time"], unit="ms") < now]
    return df[df.index <= cutoff].tail(target)

def rma(series, length):
    result = pd.Series(np.nan, index=series.index, dtype=float)
    first = series.first_valid_index()

    if first is None:
        return result

    start = series.index.get_loc(first)
    seed_values = series.iloc[start:start + length]

    if len(seed_values) < length or seed_values.isna().any():
        return result

    seed_pos = start + length - 1
    result.iloc[seed_pos] = seed_values.mean()

    for i in range(seed_pos + 1, len(series)):
        result.iloc[i] = (
            result.iloc[i - 1] * (length - 1)
            + series.iloc[i]
        ) / length

    return result

def calculate_rsi(close, length=14):
    change = close.diff()
    gain = change.clip(lower=0)
    loss = -change.clip(upper=0)

    avg_gain = rma(gain, length)
    avg_loss = rma(loss, length)

    rs = avg_gain / avg_loss
    value = 100 - (100 / (1 + rs))
    value = value.where(avg_loss != 0, 100)
    value = value.where(
        ~((avg_gain == 0) & (avg_loss == 0)), 0
    )
    return value

def audit_rsi():
    short = data["bars15"].sort_index()
    cutoff = short.index[-1]
    full = fetch_history("15m", cutoff, 1000)

    print("\n--- RSI14 | 15m ---")
    print("Historical candles:", len(full))

    short_value = calculate_rsi(short["close"]).iloc[-1]
    print(f"Snapshot 299 candles: {short_value:.12f}")

    for n in [299, 500, 1000]:
        if len(full) < n:
            continue
        value = calculate_rsi(full.tail(n)["close"]).iloc[-1]
        print(
            f"{n} candles: {value:.12f}"
            f" | diff={abs(value-short_value):.12g}"
        )

def audit_ema(label, key, interval):
    short = data[key].sort_index()
    cutoff = short.index[-1]
    full = fetch_history(interval, cutoff, 1000)

    print(f"\n--- EMA50 | {label} ---")
    print("Historical candles:", len(full))

    short_value = short["close"].ewm(
        span=50, adjust=False
    ).mean().iloc[-1]

    print(f"Snapshot 299 candles: {short_value:.12f}")

    for n in [299, 500, 1000]:
        if len(full) < n:
            continue

        value = full.tail(n)["close"].ewm(
            span=50, adjust=False
        ).mean().iloc[-1]

        print(
            f"{n} candles: {value:.12f}"
            f" | diff={abs(value-short_value):.12g}"
        )

audit_rsi()
audit_ema("1h", "bars1h", "1h")
audit_ema("4h", "bars4h", "4h")

print("\nRemaining history audit finished. No engine files changed.")
