import pandas as pd
import numpy as np

from swh_v26_engine import run_swh_v26, SWHConfig

# Generate test candles
np.random.seed(42)

def make_candles(count, start_price):
    returns = np.random.normal(0, 0.003, count)
    close = start_price * np.exp(np.cumsum(returns))
    open_price = np.roll(close, 1)
    open_price[0] = start_price

    high = np.maximum(open_price, close) * 1.002
    low = np.minimum(open_price, close) * 0.998

    volume = np.random.uniform(1000, 5000, count)

    return pd.DataFrame({
        "open": open_price,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume
    })

# Add chronological indexes (candle opening timestamps)
bars15 = make_candles(1000, 1.0)
bars1h = make_candles(300, 1.0)
bars4h = make_candles(150, 1.0)

bars15.index = pd.date_range("2026-01-01", periods=len(bars15), freq="15min")
bars1h.index = pd.date_range("2026-01-01", periods=len(bars1h), freq="1h")
bars4h.index = pd.date_range("2026-01-01", periods=len(bars4h), freq="4h")

result = run_swh_v26(
    bars15,
    bars1h,
    bars4h,
    SWHConfig()
)

print("Test completed successfully")
print("Candles:", len(result))
print("EARLY signals:", int(result["early_entry"].sum()))
print("CONFIRMED signals:", int(result["confirmed_entry"].sum()))
print("Output columns:", len(result.columns))
