import pickle
import numpy as np
import pandas as pd

with open("BARDUSDT_snapshot.pkl", "rb") as f:
    snap = pickle.load(f)

df = snap["bars15"].copy()
df = df.sort_index()

cases = [
    ("2026-11-11 08:00", "high", True),
    ("2026-11-11 08:15", "high", False),
    ("2026-11-11 13:15", "low", False),
    ("2026-11-11 13:30", "low", True),
    ("2026-11-11 17:15", "high", True),
    ("2026-11-11 19:45", "high", True),
    ("2026-11-11 21:45", "low", False),
    ("2026-11-12 00:15", "high", False),
    ("2026-11-12 00:30", "high", False),
    ("2026-11-12 00:45", "high", True),
    ("2026-11-12 11:00", "high", True),
    ("2026-11-13 05:00", "high", False),
    ("2026-11-13 05:30", "high", True),
    ("2026-11-14 00:45", "high", False),
]

print("\n=== PINE VS PYTHON PIVOT AUDIT ===")

passed = 0
failed = 0

for timestamp, kind, pine_result in cases:
    ts = pd.Timestamp(timestamp)

    if ts not in df.index:
        print(f"MISSING DATA | {timestamp}")
        failed += 1
        continue

    pos = df.index.get_loc(ts)
    values = df["high" if kind == "high" else "low"].to_numpy()

    if pos < 4 or pos + 4 >= len(df):
        print(f"INSUFFICIENT WINDOW | {timestamp}")
        failed += 1
        continue

    left = values[pos-4:pos]
    candidate = values[pos]
    right = values[pos+1:pos+5]

    if kind == "high":
        python_result = candidate >= np.max(left) and candidate > np.max(right)
    else:
        python_result = candidate <= np.min(left) and candidate < np.min(right)

    offsets = [
        i - 4 for i, value in enumerate(values[pos-4:pos+5])
        if value == candidate
    ]

    match = python_result == pine_result

    if match:
        passed += 1
    else:
        failed += 1

    print(
        f"{timestamp} | {kind.upper()} | "
        f"TIES={offsets} | "
        f"PINE={pine_result} | PYTHON={python_result} | "
        f"{'MATCH' if match else 'MISMATCH'}"
    )

print("\n==============================")
print(f"MATCHES: {passed}")
print(f"MISMATCHES: {failed}")
print("==============================")
