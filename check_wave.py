import pandas as pd
import numpy as np
from pathlib import Path

root = Path.home() / "SecondWaveHunter"
pine = pd.read_csv(root / "Pine_Combined_BARD_SOPH.csv")
py = pd.read_csv(root / "Python_Combined_BARD_SOPH.csv")

fields = {
    "wave_low": 18,
    "wave_high": 19,
    "correction_percent": 20,
}

for symbol in ["BARD", "SOPH"]:
    print("\n" + "=" * 55)
    print("PAIR:", symbol)

    p = pine[pine.SYMBOL == symbol].copy()
    x = py[py.SYMBOL == symbol].copy()

    parts = p["Message"].str.split("|", expand=True)
    p["time"] = pd.to_datetime(pd.to_numeric(parts[1]), unit="ms", utc=True)
    x["time"] = pd.to_datetime(x["open_time"], utc=True)

    for name, index in fields.items():
        p[name] = pd.to_numeric(parts[index], errors="coerce")

    merged = p.merge(x, on="time", how="inner", suffixes=("_pine", "_py"))

    for name in fields:
        a = merged[name + "_pine"]
        b = pd.to_numeric(merged[name + "_py"], errors="coerce")
        equal = np.isclose(a, b, rtol=1e-9, atol=1e-9, equal_nan=True)

        print("\n", name)
        print("Pine empty:", a.isna().sum())
        print("Python empty:", b.isna().sum())
        print("Real differences:", (~equal).sum())

        if (~equal).any():
            cols = ["time", name + "_pine", name + "_py"]
            print(merged.loc[~equal, cols].head(5).to_string(index=False))
