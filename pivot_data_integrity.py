import pickle
import pandas as pd
import numpy as np

data = pickle.load(open("BARDUSDT_snapshot.pkl", "rb"))
df = data["bars15"].sort_index()

print("DATA INTEGRITY AUDIT")
print("=" * 65)

print("\n1. INDEX")
print("Rows:", len(df))
print("Index type:", type(df.index).__name__)
print("Timezone:", df.index.tz)
print("Duplicates:", df.index.duplicated().sum())
print("Monotonic:", df.index.is_monotonic_increasing)

diffs = df.index.to_series().diff().dropna()
print("15m intervals:", (diffs == pd.Timedelta(minutes=15)).sum())
print("Other intervals:", (diffs != pd.Timedelta(minutes=15)).sum())

print("\n2. OHLC VALIDITY")
invalid = (
    (df["high"] < df[["open", "close", "low"]].max(axis=1))
    | (df["low"] > df[["open", "close", "high"]].min(axis=1))
)
print("Invalid OHLC rows:", invalid.sum())

print("\n3. CASE WINDOWS")
cases = [
    ("2026-11-11 08:00", "HIGH"),
    ("2026-11-11 08:15", "HIGH"),
    ("2026-11-11 13:15", "LOW"),
    ("2026-11-11 13:30", "LOW"),
    ("2026-11-11 17:15", "HIGH"),
    ("2026-11-11 19:45", "HIGH"),
    ("2026-11-12 00:15", "HIGH"),
    ("2026-11-12 00:30", "HIGH"),
    ("2026-11-12 00:45", "HIGH"),
    ("2026-11-13 05:00", "HIGH"),
    ("2026-11-13 05:30", "HIGH"),
    ("2026-11-14 00:45", "HIGH"),
]

for timestamp, kind in cases:
    ts = pd.Timestamp(timestamp)

    if ts not in df.index:
        print("\nMISSING:", timestamp)
        continue

    pos = df.index.get_loc(ts)
    print(f"\n{timestamp} | {kind} | position={pos}")

    for offset in range(-4, 5):
        row = df.iloc[pos + offset]
        print(
            f"{offset:+d} | {df.index[pos+offset]} | "
            f"O={row['open']} H={row['high']} "
            f"L={row['low']} C={row['close']}"
        )

print("\n4. RAW TIMESTAMP COLUMN")
if "open_time" in df.columns:
    print("open_time column exists")
    print("Index equals open_time:",
          (pd.to_datetime(df["open_time"]).to_numpy()
           == df.index.to_numpy()).all())
else:
    print("No open_time column")

print("\nAudit complete. No files changed.")
