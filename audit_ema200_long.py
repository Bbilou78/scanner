import pickle
import requests
import pandas as pd

data = pickle.load(open("BARDUSDT_snapshot.pkl", "rb"))
short = data["bars15"].copy().sort_index()

cutoff = short.index[-1]
cutoff_ms = int(cutoff.timestamp() * 1000)

url = "https://api.binance.com/api/v3/klines"
all_rows = []
end_time = cutoff_ms

print("Fetching 5000 historical 15m candles...")

while len(all_rows) < 5000:
    response = requests.get(
        url,
        params={
            "symbol": "BARDUSDT",
            "interval": "15m",
            "limit": 1000,
            "endTime": end_time
        },
        timeout=30
    )
    response.raise_for_status()
    rows = response.json()

    if not rows:
        break

    all_rows = rows + all_rows
    end_time = int(rows[0][0]) - 1

    if len(rows) < 1000:
        break

all_rows = all_rows[-5000:]

full = pd.DataFrame(all_rows, columns=[
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades",
    "taker_base", "taker_quote", "ignore"
])

full["open_time"] = pd.to_datetime(full["open_time"], unit="ms")
full["close"] = full["close"].astype(float)
full = full.set_index("open_time").sort_index()
full = full[full.index <= cutoff]

print("\nSnapshot candle:", cutoff)
print("Historical candles fetched:", len(full))

if cutoff not in full.index:
    raise RuntimeError("Snapshot final candle not found in Binance data")

print("Snapshot close:", short.loc[cutoff, "close"])
print("Binance close:", full.loc[cutoff, "close"])

short_ema = short["close"].ewm(span=200, adjust=False).mean().iloc[-1]

print("\nSnapshot EMA200:", f"{short_ema:.12f}")
print("\n--- EMA200 convergence ---")

for n in [1000, 2000, 3000, 5000]:
    sample = full.tail(n)
    ema_value = sample["close"].ewm(
        span=200, adjust=False
    ).mean().iloc[-1]

    diff = abs(ema_value - short_ema)

    print(
        f"{n} candles | EMA200={ema_value:.12f}"
        f" | diff={diff:.12f}"
    )

print("\nLong EMA200 audit finished. No engine files changed.")
