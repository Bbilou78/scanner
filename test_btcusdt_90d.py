import pandas as pd

from swh_scanner import get_klines, get_server_time
from swh_v26_engine import run_swh_v26, SWHConfig

SYMBOL = "BTCUSDT"

# 90 days test + 14 days warmup
BARS_15M = 104 * 96
BARS_1H = 104 * 24
BARS_4H = 104 * 6


def main():
    print("=" * 55)
    print("SWH v2.6 - BTCUSDT 90 DAYS HISTORICAL TEST")
    print("=" * 55)

    now = get_server_time()
    server_time = pd.to_datetime(now, unit="ms")
    test_start = server_time - pd.Timedelta(days=90)

    print("\nDownloading BTCUSDT historical candles...")

    bars15 = get_klines(SYMBOL, "15m", BARS_15M, now)
    bars1h = get_klines(SYMBOL, "1h", BARS_1H, now)
    bars4h = get_klines(SYMBOL, "4h", BARS_4H, now)

    print("\nDownloaded candles:")
    print("15m:", len(bars15))
    print("1h :", len(bars1h))
    print("4h :", len(bars4h))

    if min(len(bars15), len(bars1h), len(bars4h)) == 0:
        raise ValueError("Missing historical candle data")

    print("\nRunning original SWH v2.6 engine...")

    result = run_swh_v26(
        bars15,
        bars1h,
        bars4h,
        config=SWHConfig()
    )

    # Keep only the requested 90-day test period.
    result90 = result.loc[result.index >= test_start].copy()

    result90.to_csv("BTCUSDT_90d_all_results.csv")

    signal_frames = []

    for column, label in [
        ("early_entry", "EARLY ENTRY"),
        ("confirmed_entry", "CONFIRMED BUY")
    ]:
        selected = result90[
            result90[column].fillna(False).astype(bool)
        ].copy()

        if not selected.empty:
            selected["signal_type"] = label
            signal_frames.append(selected)

    if signal_frames:
        signals = pd.concat(signal_frames).sort_index()
        signals.index.name = "open_time"
        signals.reset_index().to_csv(
            "BTCUSDT_90d_signals.csv", index=False
        )
    else:
        signals = pd.DataFrame()
        signals.to_csv("BTCUSDT_90d_signals.csv", index=False)

    early_count = int(
        result90["early_entry"].fillna(False).sum()
    )
    confirmed_count = int(
        result90["confirmed_entry"].fillna(False).sum()
    )

    print("\n" + "=" * 55)
    print("TEST RESULTS")
    print("=" * 55)
    print("Test period starts:", test_start)
    print("Test period ends  :", server_time)
    print("15m candles tested:", len(result90))
    print("EARLY signals     :", early_count)
    print("CONFIRMED signals :", confirmed_count)

    if not signals.empty:
        print("\nHistorical signals:")
        print(
            signals[
                ["signal_type", "close", "confirmation_score"]
            ].to_string()
        )
    else:
        print("\nNo historical signals found.")

    print("\nFiles saved:")
    print("- BTCUSDT_90d_all_results.csv")
    print("- BTCUSDT_90d_signals.csv")
    print("\nTest completed. No Telegram messages were sent.")


if __name__ == "__main__":
    main()
