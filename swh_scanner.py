import json
import time
import urllib.request
import urllib.parse
from pathlib import Path
import pandas as pd

from swh_v26_engine import run_swh_v26, SWHConfig

BASE = "https://api.binance.com/api/v3/"
MAX_SYMBOLS = 50

def load_telegram_config():
    env_file = Path(__file__).with_name(".env")
    config = {}

    if not env_file.exists():
        return config

    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        config[key.strip()] = value.strip().strip('"').strip("'")

    return config


def send_telegram_message(message):
    config = load_telegram_config()
    token = config.get("TELEGRAM_BOT_TOKEN")
    chat_id = config.get("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise ValueError("Telegram credentials are missing from .env")

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message
    }).encode()

    request = urllib.request.Request(
        url,
        data=data,
        headers={"User-Agent": "SecondWaveHunter/2.6"}
    )

    with urllib.request.urlopen(request, timeout=20) as response:
        result = json.loads(response.read())

    return bool(result.get("ok"))


def api_get(endpoint, params=None):
    url = BASE + endpoint
    if params:
        url += "?" + urllib.parse.urlencode(params)

    request = urllib.request.Request(
        url,
        headers={"User-Agent": "SecondWaveHunter/2.6"}
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def get_server_time():
    return api_get("time")["serverTime"]
def get_usdt_symbols(now):
    print("Loading Binance Spot symbols...")

    exchange = api_get("exchangeInfo")
    tickers = api_get("ticker/24hr")

    excluded = {"SOXSBUSDT"}

    active = {
        item["symbol"]
        for item in exchange["symbols"]
        if item["status"] == "TRADING"
        and item["quoteAsset"] == "USDT"
        and item.get("isSpotTradingAllowed", False)
    }

    candidates = []

    for ticker in tickers:
        symbol = ticker["symbol"]
        if symbol in active and symbol not in excluded:
            change = float(ticker.get("priceChangePercent", 0))
            candidates.append((symbol, change))

    candidates.sort(key=lambda item: item[1], reverse=True)

    gainers = candidates[:MAX_SYMBOLS]

    negative_candidates = [
        item for item in candidates if item[1] < 0
    ]
    negative_candidates.sort(key=lambda item: item[1])

    losers = []

    print("Checking Top Losers candidates...")

    for symbol, change_24h in negative_candidates:
        if len(losers) >= MAX_SYMBOLS:
            break

        try:
            bars = get_klines(symbol, "1h", 72, now)

            if len(bars) < 72:
                continue

            prior_48h = bars.iloc[-72:-24]
            recent_24h = bars.iloc[-24:]

            prior_start = float(prior_48h.iloc[0]["open"])
            prior_high = float(prior_48h["high"].max())
            recent_start = float(recent_24h.iloc[0]["open"])
            recent_close = float(recent_24h.iloc[-1]["close"])

            if prior_start <= 0 or recent_start <= 0:
                continue

            prior_rise = (prior_high / prior_start - 1) * 100
            recent_change = (recent_close / recent_start - 1) * 100

            if prior_rise >= 25 and recent_change < 0:
                losers.append((symbol, change_24h))
                print(
                    f"Qualified loser: {symbol} | "
                    f"Prior rise: {prior_rise:.2f}% | "
                    f"Recent change: {recent_change:.2f}%"
                )

        except Exception as error:
            print(f"Loser check failed for {symbol}: {error}")

        time.sleep(0.08)

    selected = []
    seen = set()

    for symbol, change in gainers + losers:
        if symbol not in seen:
            selected.append((symbol, change))
            seen.add(symbol)

    print("Active USDT Spot pairs:", len(candidates))
    print("Top Gainers selected:", len(gainers))
    print("Top Losers qualified:", len(losers))
    print("Total unique symbols selected:", len(selected))

    return selected


def get_klines(symbol, interval, target_count, now):
    all_data = []
    end_time = now

    while len(all_data) < target_count:
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": 1000,
            "endTime": end_time
        }

        data = api_get("klines", params)

        if not data:
            break

        all_data.extend(data)

        oldest_time = min(candle[0] for candle in data)
        end_time = oldest_time - 1

        if len(data) < 1000:
            break

        time.sleep(0.08)

    columns = [
        "open_time", "open", "high", "low", "close",
        "volume", "close_time", "quote_volume",
        "trades", "taker_buy_base", "taker_buy_quote",
        "ignore"
    ]

    df = pd.DataFrame(all_data, columns=columns)

    if df.empty:
        return df

    df = df.drop_duplicates(subset=["open_time"])

    # Keep fully closed candles only.
    df = df[df["close_time"].astype("int64") < now]

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col])

    df["open_time"] = pd.to_datetime(
        df["open_time"], unit="ms"
    )

    df = df.set_index("open_time", drop=False).sort_index()
    return df.tail(target_count)


def scan_symbol(symbol, now):
    bars15 = get_klines(symbol, "15m", 2200, now)
    bars1h = get_klines(symbol, "1h", 600, now)
    bars4h = get_klines(symbol, "4h", 300, now)

    if min(len(bars15), len(bars1h), len(bars4h)) == 0:
        raise ValueError("Insufficient candle data")

    result = run_swh_v26(
        bars15,
        bars1h,
        bars4h,
        config=SWHConfig()
    )

    latest = result.iloc[-1]

    early = bool(latest["early_entry"])
    confirmed = bool(latest["confirmed_entry"])

    signal = "NONE"

    if confirmed:
        signal = "CONFIRMED BUY"
    elif early:
        signal = "EARLY BUY"

    # Diagnostic setup classification only - does not affect entries
    correction = latest["correction_percent"]
    wave_active = bool(latest["wave_active"])
    reversal_seen = bool(latest["reversal_seen"])

    correction_valid = (
        not pd.isna(correction)
        and 30 <= float(correction) <= 70
        and (float(correction) < 60 or reversal_seen)
    )

    resistance = (
        bars15["high"]
        .rolling(10, min_periods=10)
        .max()
        .shift(1)
        .iloc[-1]
    )

    distance_percent = None

    if not pd.isna(resistance) and float(resistance) > 0:
        distance_percent = (
            (float(resistance) - float(latest["close"]))
            / float(resistance)
        ) * 100

    setup_status = "OTHER"

    if wave_active and correction_valid:
        if distance_percent is not None and 0 <= distance_percent <= 2:
            setup_status = "NEAR BREAKOUT"
        else:
            setup_status = "ACTIVE CORRECTION"

    return {
        "symbol": symbol,
        "last_candle": str(result.index[-1]),
        "close": float(latest["close"]),
        "signal": signal,
        "setup_status": setup_status,
        "local_resistance": resistance,
        "distance_percent": distance_percent,
        "early_entry": early,
        "confirmed_entry": confirmed,
        "confirmation_score": int(latest["confirmation_score"]),
        "correction_percent": latest["correction_percent"],
        "wave_low": latest["wave_low"],
        "wave_high": latest["wave_high"],
        "volume_ready": bool(latest["vol15_ready"]),
        "momentum_ready": bool(latest["momentum_ready"]),
        "trend1h_ready": bool(latest["trend1h_ready"]),
        "vol4h_ready": bool(latest["vol4h_ready"]),
        "ema_trend_ready": bool(latest["ema_trend_ready"])
    }


def main():
    scan_started = time.time()
    print("\nScan started at:", time.strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 55)
    print("SECOND WAVE HUNTER v2.6 - BINANCE SPOT SCANNER")
    print("=" * 55)

    print("\nGetting Binance server time...")
    now = get_server_time()

    symbols = get_usdt_symbols(now)

    results = []
    errors = []

    total = len(symbols)

    for number, (symbol, quote_volume) in enumerate(symbols, 1):
        print(f"\n[{number}/{total}] Scanning {symbol}...")

        try:
            row = scan_symbol(symbol, now)
            row["change_percent_24h"] = quote_volume
            results.append(row)

            if row["signal"] != "NONE":
                print(
                    ">>> SIGNAL:",
                    row["signal"],
                    "| Score:",
                    row["confirmation_score"]
                )
            else:
                print("No current signal.")

        except Exception as error:
            print("ERROR:", str(error))
            errors.append({
                "symbol": symbol,
                "error": str(error)
            })

    if results:
        df = pd.DataFrame(results)
        df.to_csv("SWH_scan_results.csv", index=False)

        # Archive each scan without overwriting previous runs
        from datetime import datetime
        from pathlib import Path

        history_dir = Path("history")
        history_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_file = history_dir / f"SWH_scan_results_{timestamp}.csv"
        df.to_csv(archive_file, index=False)

        print(f"Archived results to {archive_file}")

        signals = df[df["signal"] != "NONE"].copy()

        # Send each signal once per symbol, signal type, and candle
        if not signals.empty:
            state_file = Path("telegram_sent_alerts.json")
            sent_keys = set()

            if state_file.exists():
                try:
                    sent_keys = set(json.loads(state_file.read_text()))
                except Exception:
                    print("WARNING: Could not read Telegram alert history.")

            for _, alert in signals.iterrows():
                alert_key = "|".join([
                    str(alert["symbol"]),
                    str(alert["signal"]),
                    str(alert["last_candle"])
                ])

                if alert_key in sent_keys:
                    continue

                message = (
                    "SECOND WAVE HUNTER v2.6\\n"
                    f"Signal: {alert['signal']}\\n"
                    f"Symbol: {alert['symbol']}\\n"
                    f"Close: {alert['close']}\\n"
                    f"Confirmation Score: {alert['confirmation_score']}\\n"
                    f"Candle: {alert['last_candle']}"
                )

                try:
                    if send_telegram_message(message):
                        sent_keys.add(alert_key)
                        state_file.write_text(
                            json.dumps(sorted(sent_keys), indent=2)
                        )
                        print("Telegram alert sent:", alert["symbol"])
                    else:
                        print("Telegram rejected alert:", alert["symbol"])

                except Exception as error:
                    print(
                        "Telegram alert failed for",
                        alert["symbol"],
                        ":",
                        str(error)
                    )


        print("\n" + "=" * 55)
        print("SCAN SUMMARY")
        print("=" * 55)
        print("Successfully scanned:", len(results))
        print("Failed pairs:", len(errors))
        print("EARLY signals:", int(df["early_entry"].sum()))
        print("CONFIRMED signals:", int(df["confirmed_entry"].sum()))

        if signals.empty:
            print("\nNo signals on the latest closed candles.")
        else:
            print("\nCURRENT SIGNALS:")
            print(signals[
                ["symbol", "signal", "close",
                 "confirmation_score", "last_candle"]
            ].to_string(index=False))

    if errors:
        pd.DataFrame(errors).to_csv(
            "SWH_scan_errors.csv", index=False
        )
        print("\nErrors saved to SWH_scan_errors.csv")

    print("\nResults saved to SWH_scan_results.csv")
    print("Scan duration: {:.1f} seconds".format(time.time() - scan_started))
    print("Scanner run completed.")


if __name__ == "__main__":
    try:
        print("\nStarting scan cycle...")
        main()
    except Exception as error:
        print("Scanner cycle failed:", str(error))
