import pandas as pd
import numpy as np
from pathlib import Path

root = Path.home() / "SecondWaveHunter"
pine = pd.read_csv(root / "Pine_Combined_BARD_SOPH.csv")
py = pd.read_csv(root / "Python_Combined_BARD_SOPH.csv")

fields = {
    "wave_low": 18,
    "wave_high": 19,
    "correction_percent": 20
}

for symbol in ["BARD", "SOPH"]:
    p = pine[pine.SYMBOL == symbol].copy()
    x = py[py.SYMBOL == symbol].copy()

    parts = p["Message"].str.split("|", expand=True)

    p["time"] = pd.to_datetime(
        pd.to_numeric(parts[1]), unit="ms", utc=True
    )
    p["active_pine"] = pd.to_numeric(parts[17], errors="coerce")

    for name, index in fields.items():
        p[name] = pd.to_numeric(parts[index], errors="coerce")

    x["time"] = pd.to_datetime(x["open_time"], utc=True)

    merged = p.merge(x, on="time", suffixes=("_pine", "_py"))

    active = merged[
        (merged["active_pine"] == 1) &
        (merged["wave_active"] == 1)
    ]

    print("\nPAIR:", symbol)
    print("Active candles:", len(active))

    for name in fields:
        a = pd.to_numeric(active[name + "_pine"], errors="coerce")
        b = pd.to_numeric(active[name + "_py"], errors="coerce")

        equal = np.isclose(
            a, b, rtol=1e-9, atol=1e-9, equal_nan=True
        )

        print(name, "- differences:", (~equal).sum())

