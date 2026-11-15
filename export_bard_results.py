import pandas as pd
from swh_v26_engine import run_swh_v26, SWHConfig

data = pd.read_pickle("BARDUSDT_snapshot.pkl")

result = run_swh_v26(
    data["bars15"],
    data["bars1h"],
    data["bars4h"],
    SWHConfig()
)

result.to_csv("BARDUSDT_python_results.csv", index=True)

print("Export successful")
print("File: BARDUSDT_python_results.csv")
print("Rows:", len(result))
print("Columns:", len(result.columns))
print("First timestamp:", result.index.min())
print("Last timestamp:", result.index.max())
