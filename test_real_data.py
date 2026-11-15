import json
import urllib.request
import urllib.parse
import pandas as pd

from swh_v26_engine import run_swh_v26, SWHConfig

BASE = "https://api.binance.com/api/v3/"

def get_server_time():
    url = BASE + "time"
    with urllib.request.urlopen(url, timeout=15) as response:
        return json.loads(response.read())["serverTime"]


def get_klines(interval, target_count, now):
    print(f"Downloading {target_count} candles: {interval}")

    all_data = []
    end_time = now

    while len(all_data) < target_count:
        params = urllib.parse.urlencode({
            "symbol": "DODOUSDT",
            "interval": interval,
            "limit": 1000,
            "endTime": end_time
        })

        url = BASE + "klines?" + params

        with urllib.request.urlopen(url, timeout=30) as response:
            data = json.loads(response.read())

        if not data:
            break

        all_data.extend(data)

        oldest_time = min(c[0] for c in data)
        end_time = oldest_time - 1

        if len(data) < 1000:
            break

    df = pd.DataFrame(all_data, columns=[
        "open_time", "open", "high", "low", "close",
        "volume", "close_time", "quote_volume",
        "trades", "taker_buy_base", "taker_buy_quote",
        "ignore"
    ])

    df = df.drop_duplicates(subset=["open_time"])

    # Keep only fully closed candles.
    df = df[df["close_time"].astype("int64") < now]

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col])

    df["open_time"] = pd.to_datetime(
        df["open_time"], unit="ms"
    )

    df = df.set_index("open_time", drop=False).sort_index()
    df = df.tail(target_count)

    return df


print("Getting Binance server time...")
now = get_server_time()

print("\nDownloading historical DODOUSDT data...")

bars15 = get_klines("15m", 2200, now)
bars1h = get_klines("1h", 600, now)
bars4h = get_klines("4h", 300, now)

print("\n--- Download Summary ---")
print("15m candles:", len(bars15))
print("1h candles:", len(bars1h))
print("4h candles:", len(bars4h))

print("\nRunning Second Wave Hunter v2.6...")

result = run_swh_v26(
    bars15,
    bars1h,
    bars4h,
    config=SWHConfig()
)

print("\n--- Engine Results ---")
print("Output columns:", len(result.columns))
print("EARLY signals:", int(result["early_entry"].sum()))
print("CONFIRMED signals:", int(result["confirmed_entry"].sum()))

print("\n--- Indicator Warmup Check ---")
for col in ["ema20", "ema50", "ema200", "rsi", "volume_sma20"]:
    print(
        col,
        "| First valid:",
        result[col].first_valid_index(),
        "| Last value:",
        result[col].iloc[-1]
    )

print("\n--- EARLY SIGNAL DETAILS ---")

cols = [
    "close",
    "wave_low",
    "wave_high",
    "correction_percent",
    "reversal_seen",
    "breakout_fresh",
    "vol15_ready",
    "momentum_ready",
    "ema_trend_ready",
    "trend1h_ready",
    "vol4h_ready",
    "confirmation_score",
    "early_entry",
    "confirmed_entry",
    "last_signal"
]

signals = result[result["early_entry"] | result["confirmed_entry"]]

if signals.empty:
    print("No entry signals found.")
else:
    print(signals[cols].to_string())

output_file = "DODOUSDT_python_results.csv"
result.to_csv(output_file)

print("\nResults exported to:", output_file)
print("Engine test completed successfully.")
