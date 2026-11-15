import pandas as pd
from swh_v26_engine import run_swh_v26, SWHConfig

data = pd.read_pickle("BARDUSDT_snapshot.pkl")

bars15 = data["bars15"].copy()
bars1h = data["bars1h"].copy()
bars4h = data["bars4h"].copy()

print("BARDUSDT SNAPSHOT TEST")
print("=" * 45)

result = run_swh_v26(
    bars15,
    bars1h,
    bars4h,
    SWHConfig()
)

print("Test completed successfully")
print("15m candles:", len(bars15))
print("1h candles:", len(bars1h))
print("4h candles:", len(bars4h))
print("Output rows:", len(result))
print("Output columns:", len(result.columns))
print("EARLY signals:", int(result["early_entry"].sum()))
print("CONFIRMED signals:", int(result["confirmed_entry"].sum()))

signals = result[
    result["early_entry"] | result["confirmed_entry"]
]

if not signals.empty:
    print("\nSIGNAL DETAILS:")
    cols = [
        c for c in [
            "close", "early_entry", "confirmed_entry",
            "correction_percent", "wave_active"
        ] if c in signals.columns
    ]
    print(signals[cols].to_string())
else:
    print("\nNo signals generated on this snapshot.")
