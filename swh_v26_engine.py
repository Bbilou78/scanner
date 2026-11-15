import numpy as np
import pandas as pd
from dataclasses import dataclass


@dataclass
class SWHConfig:
    min_pump: float = 25.0
    min_retrace: float = 30.0
    max_retrace: float = 70.0
    deep_level: float = 60.0
    pivot_len: int = 4
    breakout_len: int = 10
    max_setup_bars: int = 160
    vol15_multiplier: float = 1.2
    vol4h_multiplier: float = 1.3
    confirmation_bars: int = 3
    use_ema200: bool = True
    min_wave_bars: int = 4


def ema(series, length):
    return series.ewm(span=length, adjust=False).mean()


def rma(series, length):
    result = pd.Series(np.nan, index=series.index, dtype=float)

    if len(series) < length:
        return result

    first = series.first_valid_index()
    if first is None:
        return result

    start = series.index.get_loc(first)
    seed_values = series.iloc[start:start + length]

    if len(seed_values) < length or seed_values.isna().any():
        return result

    seed_pos = start + length - 1
    result.iloc[seed_pos] = seed_values.mean()

    for i in range(seed_pos + 1, len(series)):
        result.iloc[i] = (
            result.iloc[i - 1] * (length - 1)
            + series.iloc[i]
        ) / length

    return result


def rsi(series, length=14):
    change = series.diff()
    gain = change.clip(lower=0)
    loss = -change.clip(upper=0)

    avg_gain = rma(gain, length)
    avg_loss = rma(loss, length)

    rs = avg_gain / avg_loss
    value = 100 - (100 / (1 + rs))

    value = value.where(avg_loss != 0, 100)
    value = value.where(
        ~((avg_gain == 0) & (avg_loss == 0)), 0
    )
    return value


def sma(series, length):
    return series.rolling(length, min_periods=length).mean()


def pivot_at(values, pos, length, is_low):
    left = pos - length
    right = pos + length

    if left < 0 or right >= len(values):
        return False

    candidate = values[pos]
    left_values = values[left:pos]
    right_values = values[pos + 1:right + 1]

    if is_low:
        return (
            candidate <= np.min(left_values)
            and candidate < np.min(right_values)
        )

    return (
        candidate >= np.max(left_values)
        and candidate > np.max(right_values)
    )


def prepare_htf(df, prefix):
    data = df.copy().sort_index()

    data[f"{prefix}_ema50"] = ema(data["close"], 50)
    data[f"{prefix}_vol_sma20"] = sma(data["volume"], 20)

    return data


def map_previous_htf(base, htf, prefix):
    result = pd.DataFrame(index=base.index)

    columns = {
        f"{prefix}_close": "close",
        f"{prefix}_ema50": f"{prefix}_ema50",
        f"{prefix}_volume": "volume",
        f"{prefix}_vol_sma20": f"{prefix}_vol_sma20",
    }

    if htf is None or htf.empty:
        for output_col in columns:
            result[output_col] = np.nan
        return result

    htf = prepare_htf(htf, prefix)

    # Make each HTF candle available at its closing timestamp.
    available = htf.copy()
    available.index = available.index + pd.Timedelta({"h1": "1h", "h4": "4h"}.get(prefix, prefix))
    available = available.sort_index()

    for output_col, source_col in columns.items():
        result[output_col] = available[source_col].reindex(
            base.index, method="ffill"
        )

    return result


def run_swh_v26(bars15, bars1h, bars4h, config=None):
    """
    Input:
        bars15, bars1h, bars4h:
            DataFrames indexed by candle opening time.
            Required columns: open, high, low, close, volume.

    Output:
        DataFrame containing indicator values and entry signals.
    """

    cfg = config or SWHConfig()

    required = ["open", "high", "low", "close", "volume"]

    df = bars15.copy().sort_index()

    for col in required:
        if col not in df.columns:
            raise ValueError(f"Missing column: {col}")

    df = df[required].astype(float)

    if df.empty:
        return df

    # ------------------------------------------
    # Indicators
    # ------------------------------------------

    df["ema20"] = ema(df["close"], 20)
    df["ema50"] = ema(df["close"], 50)
    df["ema200"] = ema(df["close"], 200)

    df["rsi"] = rsi(df["close"], 14)
    df["volume_sma20"] = sma(df["volume"], 20)

    df["vol15_ready"] = (
        df["volume"] >
        df["volume_sma20"] * cfg.vol15_multiplier
    )

    df["momentum_ready"] = (
        (df["close"] > df["ema20"]) &
        (df["rsi"] >= 48)
    )

    df["ema_trend_ready"] = (
        True if not cfg.use_ema200
        else df["close"] > df["ema200"]
    )

    # ------------------------------------------
    # Higher timeframe filters
    # ------------------------------------------

    h1 = map_previous_htf(df, bars1h, "h1")
    h4 = map_previous_htf(df, bars4h, "h4")

    df = df.join(h1).join(h4)

    df["trend1h_ready"] = (
        df["h1_close"] > df["h1_ema50"]
    )

    df["vol4h_ready"] = (
        df["h4_volume"] >
        df["h4_vol_sma20"] * cfg.vol4h_multiplier
    )

    # ------------------------------------------
    # Reversal candles
    # ------------------------------------------

    prev_open = df["open"].shift(1)
    prev_close = df["close"].shift(1)

    bullish_engulfing = (
        (df["close"] > df["open"]) &
        (prev_close < prev_open) &
        (df["close"] >= prev_open) &
        (df["open"] <= prev_close)
    )

    body = (df["close"] - df["open"]).abs()
    lower_wick = (
        np.minimum(df["open"], df["close"]) - df["low"]
    )
    upper_wick = (
        df["high"] - np.maximum(df["open"], df["close"])
    )

    hammer = (
        (df["close"] > df["open"]) &
        (lower_wick >= body * 2) &
        (upper_wick <= body)
    )

    piercing = (
        (prev_close < prev_open) &
        (df["close"] > df["open"]) &
        (df["close"] > (prev_open + prev_close) / 2) &
        (df["open"] < prev_close)
    )

    reversal = bullish_engulfing | hammer | piercing

    # ------------------------------------------
    # Pivot detection
    # ------------------------------------------

    lows = df["low"].to_numpy()
    highs = df["high"].to_numpy()

    pivot_lows = []
    pivot_highs = []

    for i in range(len(df)):
        pos = i - cfg.pivot_len

        if pos < cfg.pivot_len:
            pivot_lows.append(None)
            pivot_highs.append(None)
            continue

        is_low = pivot_at(
            lows, pos, cfg.pivot_len, True
        )
        is_high = pivot_at(
            highs, pos, cfg.pivot_len, False
        )

        pivot_lows.append(
            (lows[pos], pos) if is_low else None
        )
        pivot_highs.append(
            (highs[pos], pos) if is_high else None
        )

    # ------------------------------------------
    # State machine
    # ------------------------------------------

    n = len(df)

    output = {
        "pivot_low": [],
        "pivot_high": [],
        "wave_active": [],
        "wave_low": [],
        "wave_high": [],
        "correction_percent": [],
        "reversal_seen": [],
        "breakout_fresh": [],
        "confirmation_score": [],
        "early_entry": [],
        "confirmed_entry": [],
        "last_signal": [],
    }

    confirmed_lows = []
    last_used_low_bar = None

    wave_low = np.nan
    wave_high = np.nan
    correction_low = np.nan

    wave_start_bar = None
    wave_active = False
    wave_invalid = False
    reversal_seen = False

    early_fired = False
    confirmed_fired = False

    breakout_bar = None
    last_signal = "NONE"

    local_resistance = (
        df["high"].rolling(
            cfg.breakout_len,
            min_periods=cfg.breakout_len
        ).max().shift(1)
    )

    for i in range(n):

        row = df.iloc[i]

        # Store confirmed pivot lows.
        pl = pivot_lows[i]
        ph = pivot_highs[i]

        if pl is not None:
            confirmed_lows.append(pl)

        # --------------------------------------
        # First wave detection
        # --------------------------------------

        new_wave = False

        if ph is not None and confirmed_lows:
            pivot_price, pivot_bar = ph

            for candidate_price, candidate_bar in reversed(
                confirmed_lows
            ):
                bars_between = pivot_bar - candidate_bar

                valid_low = (
                    bars_between >= cfg.min_wave_bars
                    and (
                        last_used_low_bar is None
                        or candidate_bar > last_used_low_bar
                    )
                    and pivot_price >= candidate_price * (
                        1 + cfg.min_pump / 100
                    )
                )

                if valid_low:
                    wave_low = candidate_price
                    wave_high = pivot_price
                    wave_start_bar = pivot_bar

                    # Pine ta.lowest(low, pivotLen + 1)
                    start = max(0, i - cfg.pivot_len)
                    correction_low = float(
                        df["low"].iloc[start:i + 1].min()
                    )

                    wave_active = True
                    wave_invalid = False
                    reversal_seen = False

                    early_fired = False
                    confirmed_fired = False
                    breakout_bar = None

                    last_used_low_bar = candidate_bar
                    new_wave = True
                    break

        # --------------------------------------
        # Correction tracking
        # --------------------------------------

        if wave_active and wave_start_bar is not None:
            if i > wave_start_bar:
                correction_low = min(
                    correction_low, float(row["low"])
                )

            wave_invalid = correction_low <= wave_low

        wave_range = wave_high - wave_low

        correction_percent = (
            (wave_high - correction_low) / wave_range * 100
            if wave_active and wave_range > 0
            else np.nan
        )

        too_deep = (
            wave_active
            and not np.isnan(correction_percent)
            and correction_percent > cfg.max_retrace
        )

        setup_expired = (
            wave_active
            and wave_start_bar is not None
            and i - wave_start_bar > cfg.max_setup_bars
        )

        if setup_expired or wave_invalid or too_deep:
            wave_active = False
            breakout_bar = None
            reversal_seen = False

        correction_ready = (
            wave_active
            and not wave_invalid
            and not too_deep
            and not np.isnan(correction_percent)
            and cfg.min_retrace <= correction_percent
            <= cfg.max_retrace
        )

        deep_correction = (
            correction_ready
            and correction_percent >= cfg.deep_level
        )

        # --------------------------------------
        # Reversal confirmation
        # --------------------------------------

        if (
            wave_active
            and correction_ready
            and bool(reversal.iloc[i])
        ):
            reversal_seen = True

        correction_confirmation_ready = (
            correction_ready
            and (not deep_correction or reversal_seen)
        )

        # --------------------------------------
        # Local breakout
        # --------------------------------------

        resistance = local_resistance.iloc[i]

        raw_breakout = (
            not pd.isna(resistance)
            and row["close"] > resistance
        )

        breakout_event = (
            raw_breakout
            and correction_confirmation_ready
        )

        if breakout_event:
            breakout_bar = i

        breakout_fresh = (
            wave_active
            and correction_ready
            and breakout_bar is not None
            and i - breakout_bar <= cfg.confirmation_bars
        )

        # --------------------------------------
        # Early entry
        # --------------------------------------

        early_core = (
            breakout_fresh
            and bool(df["vol15_ready"].iloc[i])
            and bool(df["momentum_ready"].iloc[i])
        )

        early_entry = early_core and not early_fired

        # --------------------------------------
        # Confirmed entry
        # --------------------------------------

        score = (
            int(bool(df["vol4h_ready"].iloc[i]))
            + int(bool(df["trend1h_ready"].iloc[i]))
            + int(bool(df["ema_trend_ready"].iloc[i]))
        )

        confirmed_entry = (
            early_core
            and score >= 2
            and not confirmed_fired
        )

        if early_entry:
            early_fired = True

        if confirmed_entry:
            confirmed_fired = True

        if confirmed_entry:
            last_signal = "CONFIRMED BUY"
        elif early_entry:
            last_signal = "EARLY ENTRY"

        # --------------------------------------
        # Save results
        # --------------------------------------

        output["pivot_low"].append(pl is not None)
        output["pivot_high"].append(ph is not None)
        output["wave_active"].append(wave_active)
        output["wave_low"].append(wave_low)
        output["wave_high"].append(wave_high)
        output["correction_percent"].append(
            correction_percent
        )
        output["reversal_seen"].append(reversal_seen)
        output["breakout_fresh"].append(breakout_fresh)
        output["confirmation_score"].append(score)
        output["early_entry"].append(early_entry)
        output["confirmed_entry"].append(confirmed_entry)
        output["last_signal"].append(last_signal)

    for key, values in output.items():
        df[key] = values

    return df
