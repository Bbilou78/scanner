import pickle
import pandas as pd

data = pickle.load(open("BARDUSDT_snapshot.pkl", "rb"))
df = data["bars15"].sort_index()

cases = [
    ("2026-11-11 08:00", "HIGH", True),
    ("2026-11-11 08:15", "HIGH", False),
    ("2026-11-11 13:15", "LOW", False),
    ("2026-11-11 13:30", "LOW", True),
    ("2026-11-11 17:15", "HIGH", True),
    ("2026-11-11 19:45", "HIGH", True),
    ("2026-11-11 21:45", "LOW", False),
    ("2026-11-12 00:15", "HIGH", False),
    ("2026-11-12 00:30", "HIGH", False),
    ("2026-11-12 00:45", "HIGH", True),
    ("2026-11-12 11:00", "HIGH", True),
    ("2026-11-13 05:00", "HIGH", False),
    ("2026-11-13 05:30", "HIGH", False),
]

print("PIVOT TIE AUDIT")
print("Pivot length: 4")
print("Window: 4 candles left + candidate + 4 candles right")

for timestamp, kind, pine_result in cases:
    ts = pd.Timestamp(timestamp)
    if ts not in df.index:
        print(f"\nMISSING: {timestamp}")
        continue

    pos = df.index.get_loc(ts)
    if pos < 4 or pos + 4 >= len(df):
        print(f"\nINSUFFICIENT WINDOW: {timestamp}")
        continue

    column = "high" if kind == "HIGH" else "low"
    window = df.iloc[pos - 4:pos + 5][column].astype(float)
    candidate = float(df.iloc[pos][column])

    extreme = window.max() if kind == "HIGH" else window.min()
    offsets = list(range(-4, 5))
    tied_offsets = [
        offsets[i] for i, value in enumerate(window)
        if value == extreme
    ]

    left = [x for x in tied_offsets if x < 0]
    right = [x for x in tied_offsets if x > 0]

    print(f"\n{timestamp} | {kind} | Pine={int(pine_result)}")
    print(f"Candidate={candidate:.10f} | Window extreme={extreme:.10f}")
    print(f"Tied offsets={tied_offsets}")
    print(f"Left ties={left} | Right ties={right}")
    print("Window:")
    for offset, (time, value) in zip(offsets, window.items()):
        mark = "*" if float(value) == extreme else " "
        print(f"  {offset:+d} {time} {float(value):.10f} {mark}")

print("\nAudit complete. No files changed.")
