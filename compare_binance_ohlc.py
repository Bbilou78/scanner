import pickle
import requests
import pandas as pd

data = pickle.load(open("BARDUSDT_snapshot.pkl", "rb"))
df = data["bars15"].sort_index()

times = [
    "2026-11-11 08:00",
    "2026-11-11 08:15",
    "2026-11-11 13:15",
    "2026-11-11 13:30",
    "2026-11-11 17:15",
    "2026-11-11 19:45",
    "2026-11-12 00:15",
    "2026-11-12 00:30",
    "2026-11-12 00:45",
    "2026-11-13 05:00",
    "2026-11-13 05:30",
    "2026-11-14 00:45",
]

start = int(pd.Timestamp(times[0], tz="UTC").timestamp() * 1000)
end = int((pd.Timestamp(times[-1], tz="UTC") + pd.Timedelta(minutes=15)).timestamp() * 1000)

url = "https://api.binance.com/api/v3/klines"
response = requests.get(
    url,
    params={
        "symbol": "BARDUSDT",
        "interval": "15m",
        "startTime": start,
        "endTime": end,
        "limit": 1000,
    },
    timeout=20,
)
response.raise_for_status()

raw = response.json()
remote = pd.DataFrame(raw, columns=[
    "open_time", "open", "high", "low", "close", "volume",
    "close_time", "quote_volume", "trades",
    "taker_buy_base", "taker_buy_quote", "ignore"
])

remote["open_time"] = pd.to_datetime(remote["open_time"], unit="ms")
remote = remote.set_index("open_time")

print("BINANCE VS SNAPSHOT")
print("=" * 65)

for t in times:
    ts = pd.Timestamp(t)

    if ts not in df.index or ts not in remote.index:
        print(t, "| MISSING")
        continue

    local = df.loc[ts]
    live = remote.loc[ts]

    diffs = {}
    for col in ["open", "high", "low", "close"]:
        a = float(local[col])
        b = float(live[col])
        diffs[col] = abs(a - b)

    match = all(v == 0 for v in diffs.values())

    print(
        t,
        "| MATCH =", match,
        "| diffs =", diffs
    )

print("\nComparison complete. No engine files changed.")
