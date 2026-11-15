import pandas as pd
import numpy as np
from pathlib import Path

root = Path.home() / "SecondWaveHunter"
pine = pd.read_csv(root / "Pine_Combined_BARD_SOPH.csv")
py = pd.read_csv(root / "Python_Combined_BARD_SOPH.csv")

fields = {
    "vol15_ready": 23,
    "momentum_ready": 24,
    "trend1h_ready": 25,
    "vol4h_ready": 26,
    "ema_trend_ready": 27,
    "confirmation_score": 28
}

def to_bool(series):
    return (
        series.astype(str).str.strip().str.lower()
        .map({"true": 1, "false": 0, "1": 1, "0": 0})
    )

for symbol in ["BARD", "SOPH"]:
    p = pine[pine.SYMBOL == symbol].copy()
    x = py[py.SYMBOL == symbol].copy()

    parts = p["Message"].str.split("|", expand=True)

    p["time"] = pd.to_datetime(
        pd.to_numeric(parts[1]), unit="ms", utc=True
    )

    for name, index in fields.items():
        p[name] = pd.to_numeric(parts[index], errors="coerce")

    x["time"] = pd.to_datetime(x["open_time"], utc=True)

    merged = p.merge(x, on="time", suffixes=("_pine", "_py"))

    print("\n==========", symbol, "==========")
    print("Matched candles:", len(merged))

    for name in fields:
        a = merged[name + "_pine"]
        b = merged[name + "_py"]

        if name != "confirmation_score":
            a = to_bool(a)
            b = to_bool(b)

        a = pd.to_numeric(a, errors="coerce")
        b = pd.to_numeric(b, errors="coerce")

        equal = np.isclose(
            a, b, rtol=1e-9, atol=1e-9, equal_nan=True
        )

        print(name, "- differences:", (~equal).sum())

        if (~equal).any():
            print("Examples:")
            print(merged.loc[~equal, ["time"]].head(5).to_string(index=False))
            print("Pine:", a[~equal].head(5).tolist())
            print("Python:", b[~equal].head(5).tolist())

