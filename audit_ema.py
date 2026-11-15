import pickle
import requests
import pandas as pd

data = pickle.load(open("BARDUSDT_snapshot.pkl", "rb"))

def fetch(interval):
    url = "https://api.binance.com/api/v3/klines"
    response = requests.get(
        url,
        params={"symbol": "BARDUSDT", "interval": interval, "limit": 1000},
        timeout=20
    )
    response.raise_for_status()
    rows = response.json()
    df = pd.DataFrame(rows, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_volume", "trades",
        "taker_base", "taker_quote", "ignore"
    ])
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms")
    df["close"] = df["close"].astype(float)
    df = df.set_index("open_time").sort_index()
    now = pd.Timestamp.now(tz="UTC").tz_localize(None)
    return df[pd.to_datetime(df["close_time"], unit="ms") < now]

def audit(label, short, interval, lengths):
    full = fetch(interval)
    cutoff = (
        short.index[-1] if interval == "15m"
        else short.index[-1].floor(interval) - pd.Timedelta(interval)
    )
    full = full.loc[full.index <= cutoff]

    print(f"\n--- {label} ---")
    print("Extended candles:", len(full))

    for length in lengths:
        a = short["close"].ewm(span=length, adjust=False).mean()
        b = full["close"].ewm(span=length, adjust=False).mean()
        common = a.index.intersection(b.index)
        common = common[common <= cutoff]
        diff = (a.loc[common] - b.loc[common]).abs()
        print(
            f"EMA{length}: compared={len(common)}"
            f" | max_diff={diff.max():.12g}"
            f" | last_diff={diff.iloc[-1]:.12g}"
        )

audit("15m", data["bars15"], "15m", [20, 50, 200])
audit("1h", data["bars1h"], "1h", [50])
audit("4h", data["bars4h"], "4h", [50])

print("\nEMA history audit finished. No files changed.")
