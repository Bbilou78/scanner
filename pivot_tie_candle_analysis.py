import pickle
import pandas as pd

data = pickle.load(open("BARDUSDT_snapshot.pkl", "rb"))
df = data["bars15"].sort_index()

LENGTH = 4

pine_results = {
    "2026-11-11 08:00": 1,
    "2026-11-11 08:15": 0,
    "2026-11-11 13:15": 0,
    "2026-11-11 13:30": 1,
    "2026-11-11 17:15": 1,
    "2026-11-11 19:45": 1,
    "2026-11-11 21:45": 0,
    "2026-11-12 00:15": 0,
    "2026-11-12 00:30": 0,
    "2026-11-12 00:45": 1,
    "2026-11-12 11:00": 1,
    "2026-11-13 05:00": 0,
    "2026-11-13 05:30": 0,
}

for kind, column in [("HIGH", "high"), ("LOW", "low")]:
    values = df[column].astype(float).to_numpy()

    print("\n" + "=" * 90)
    print(kind, "DETAILED CANDLE ANALYSIS")
    print("=" * 90)

    for pos in range(LENGTH, len(df) - LENGTH):
        window = values[pos-LENGTH:pos+LENGTH+1]
        candidate = values[pos]
        extreme = window.max() if kind == "HIGH" else window.min()

        if candidate != extreme:
            continue

        offsets = [
            i - LENGTH
            for i, value in enumerate(window)
            if value == extreme
        ]

        if len(offsets) < 2:
            continue

        timestamp = df.index[pos]
        key = timestamp.strftime("%Y-%m-%d %H:%M")
        pine = pine_results.get(key, None)

        print(f"\n{key} | {kind} | Pine={pine if pine is not None else 'UNKNOWN'}")
        print(f"Extreme={extreme:.10f} | Tied offsets={offsets}")

        for offset in offsets:
            row = df.iloc[pos + offset]
            o = float(row["open"])
            h = float(row["high"])
            l = float(row["low"])
            c = float(row["close"])
            v = float(row["volume"])

            body = abs(c - o)
            upper = h - max(o, c)
            lower = min(o, c) - l
            direction = "GREEN" if c > o else "RED" if c < o else "DOJI"

            print(
                f"  offset={offset:+d} time={df.index[pos+offset]} "
                f"O={o:.10f} H={h:.10f} L={l:.10f} C={c:.10f} "
                f"V={v:.2f} {direction} "
                f"body={body:.10f} upper={upper:.10f} lower={lower:.10f}"
            )

print("\nAnalysis complete. No engine files changed.")
