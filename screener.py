import os
import time
import json
from datetime import datetime, timedelta

import pandas as pd
from kiteconnect import KiteConnect
from ta.trend import EMAIndicator, MACD, ADXIndicator
from ta.momentum import RSIIndicator
from ta.volume import OnBalanceVolumeIndicator

# ---------- CONFIG ----------
KITE_API_KEY = os.environ["KITE_API_KEY"]
KITE_API_SECRET = os.environ["KITE_API_SECRET"]
REQUEST_TOKEN = os.environ["REQUEST_TOKEN"]

LOOKBACK_DAYS = 300
SLEEP_BETWEEN_CALLS = 0.34
TOP_N_PER_SECTION = 30
PENNY_THRESHOLD = 50  # price-based proxy only — Kite has no real index membership data

# ---------- LOGIN ----------
kite = KiteConnect(api_key=KITE_API_KEY)
session_data = kite.generate_session(REQUEST_TOKEN, api_secret=KITE_API_SECRET)
kite.set_access_token(session_data["access_token"])
print("Logged in as:", kite.profile()["user_name"])

# ---------- FULL NSE EQUITY UNIVERSE ----------
print("Fetching full NSE instrument list...")
instruments = kite.instruments("NSE")
instruments_df = pd.DataFrame(instruments)
instruments_df = instruments_df[instruments_df["instrument_type"] == "EQ"]
instruments_df = instruments_df[~instruments_df["tradingsymbol"].str.contains(r"-", na=False)]

symbol_to_token = dict(zip(instruments_df["tradingsymbol"], instruments_df["instrument_token"].astype(int)))
print(f"Scanning {len(symbol_to_token)} NSE-listed equities. This will take a while.")


def fetch_candles(token):
    to_date = datetime.now()
    from_date = to_date - timedelta(days=LOOKBACK_DAYS)
    candles = kite.historical_data(token, from_date, to_date, "day")
    df = pd.DataFrame(candles)
    return None if df.empty else df


def detect_patterns(df):
    reasons = []
    score = 0
    last = df.iloc[-1]
    prev = df.iloc[-2]
    prev2 = df.iloc[-3]

    body = abs(last["close"] - last["open"])
    candle_range = last["high"] - last["low"]
    lower_wick = min(last["open"], last["close"]) - last["low"]
    upper_wick = last["high"] - max(last["open"], last["close"])
    avg_vol_20 = df["volume"].tail(21).iloc[:-1].mean()

    if candle_range > 0 and lower_wick > 2 * body and upper_wick < body:
        recent_low = df["low"].tail(20).min()
        if last["low"] <= recent_low * 1.03:
            score += 14
            reasons.append("Hammer candle near recent support (bullish reversal signal)")

    if (prev["close"] < prev["open"] and last["close"] > last["open"]
            and last["close"] > prev["open"] and last["open"] < prev["close"]):
        score += 14
        reasons.append("Bullish engulfing pattern (buyers overwhelmed sellers)")

    if (prev2["close"] < prev2["open"]
            and abs(prev["close"] - prev["open"]) < (prev2["high"] - prev2["low"]) * 0.3
            and last["close"] > last["open"]
            and last["close"] > (prev2["open"] + prev2["close"]) / 2):
        score += 16
        reasons.append("Morning star pattern (strong bullish reversal)")

    if (prev["close"] > prev["open"] and last["close"] < last["open"]
            and last["close"] < prev["open"] and last["open"] > prev["close"]):
        score -= 12
        reasons.append("Bearish engulfing pattern (warning sign)")

    if candle_range > 0 and upper_wick > 2 * body and lower_wick < body:
        recent_high = df["high"].tail(20).max()
        if last["high"] >= recent_high * 0.97:
            score -= 10
            reasons.append("Shooting star near recent high (bearish warning)")

    recent_high_20 = df["high"].tail(21).iloc[:-1].max()
    if last["close"] > recent_high_20 and avg_vol_20 > 0 and last["volume"] > 1.5 * avg_vol_20:
        score += 12
        reasons.append("Breakout above 20-day high on strong volume")

    support = df["low"].tail(60).min()
    if support > 0 and 0 < (last["close"] - support) / support < 0.05:
        score += 6
        reasons.append("Price near 60-day support level")

    resistance = df["high"].tail(60).max()
    if resistance > 0 and 0 < (resistance - last["close"]) / resistance < 0.02:
        score -= 4
        reasons.append("Price right at 60-day resistance (may struggle to break out)")

    return max(min(score, 40), -20), reasons


def score_trend_momentum(df):
    reasons = []
    score = 0
    ema50 = EMAIndicator(df["close"], window=50).ema_indicator()
    ema200 = EMAIndicator(df["close"], window=200).ema_indicator()
    rsi = RSIIndicator(df["close"], window=14).rsi()
    macd = MACD(df["close"])
    adx = ADXIndicator(df["high"], df["low"], df["close"], window=14).adx()
    last_close = df["close"].iloc[-1]

    if not ema50.isna().iloc[-1] and last_close > ema50.iloc[-1]:
        score += 7
        reasons.append("Price above EMA50 (short-term uptrend)")
    else:
        score -= 4

    if not ema200.isna().iloc[-1] and last_close > ema200.iloc[-1]:
        score += 7
        reasons.append("Price above EMA200 (long-term uptrend)")
    else:
        score -= 4

    if (not ema50.isna().iloc[-1] and not ema200.isna().iloc[-1]
            and ema50.iloc[-1] > ema200.iloc[-1]
            and ema50.iloc[-2] <= ema200.iloc[-2]):
        score += 6
        reasons.append("Golden cross (EMA50 crossed above EMA200)")

    last_rsi = rsi.iloc[-1]
    if 40 <= last_rsi <= 65:
        score += 5
        reasons.append(f"RSI in healthy range ({last_rsi:.0f})")
    elif 30 <= last_rsi < 40:
        score += 7
        reasons.append(f"RSI rebounding from oversold ({last_rsi:.0f})")
    elif last_rsi > 75:
        score -= 6
        reasons.append(f"RSI overbought ({last_rsi:.0f}) - pullback risk")

    macd_line = macd.macd()
    macd_signal = macd.macd_signal()
    if (macd_line.iloc[-2] < macd_signal.iloc[-2]
            and macd_line.iloc[-1] > macd_signal.iloc[-1]):
        score += 7
        reasons.append("MACD bullish crossover (momentum turning up)")
    elif (macd_line.iloc[-2] > macd_signal.iloc[-2]
            and macd_line.iloc[-1] < macd_signal.iloc[-1]):
        score -= 5
        reasons.append("MACD bearish crossover (momentum turning down)")

    last_adx = adx.iloc[-1]
    if last_adx > 25:
        score += 4
        reasons.append(f"Strong trend in place (ADX {last_adx:.0f})")

    return max(min(score, 30), -15), reasons


def score_volume(df):
    reasons = []
    score = 0
    obv = OnBalanceVolumeIndicator(df["close"], df["volume"]).on_balance_volume()
    obv_change = obv.iloc[-1] - obv.iloc[-15]
    price_change = df["close"].iloc[-1] - df["close"].iloc[-15]

    if obv_change > 0 and price_change <= 0:
        score += 10
        reasons.append("Quiet accumulation: OBV rising while price flat (smart-money buying)")
    elif obv_change > 0 and price_change > 0:
        score += 5
        reasons.append("Volume confirms upward price move")
    elif obv_change < 0 and price_change > 0:
        score -= 6
        reasons.append("Distribution warning: price up but OBV falling")

    avg_vol_20 = df["volume"].tail(21).iloc[:-1].mean()
    last_vol = df["volume"].iloc[-1]
    if avg_vol_20 > 0 and last_vol > 2 * avg_vol_20:
        if df["close"].iloc[-1] > df["open"].iloc[-1]:
            score += 10
            reasons.append(f"Unusual buying volume ({last_vol / avg_vol_20:.1f}x average)")
        else:
            score -= 6
            reasons.append(f"Unusual selling volume ({last_vol / avg_vol_20:.1f}x average)")

    return max(min(score, 20), -10), reasons


def passes_sanity(df):
    if len(df) < 200:
        return False
    if df["volume"].tail(20).mean() < 5000:
        return False
    last_close = df["close"].iloc[-1]
    prev_close = df["close"].iloc[-2]
    if prev_close > 0 and abs(last_close - prev_close) / prev_close > 0.20:
        return False
    return True


def plain_summary(pattern_score, trend_score, volume_score, total_score):
    if total_score >= 60:
        tier = "a very strong"
    elif total_score >= 40:
        tier = "a strong"
    elif total_score >= 20:
        tier = "a moderate"
    else:
        tier = "a weak"

    drivers = []
    if pattern_score >= 20:
        drivers.append("a bullish chart pattern forming")
    if trend_score >= 15:
        drivers.append("a healthy upward trend")
    if volume_score >= 10:
        drivers.append("unusually high buying volume")

    if drivers:
        return f"This stock shows {tier} setup, mainly because of {' and '.join(drivers)}."
    return f"This stock shows {tier} setup based on overall technical signals."


# ---------- MAIN ----------
all_results = []
total = len(symbol_to_token)
errors = 0

for i, (symbol, token) in enumerate(symbol_to_token.items(), start=1):
    try:
        df = fetch_candles(token)
        time.sleep(SLEEP_BETWEEN_CALLS)
        if df is None or not passes_sanity(df):
            continue

        pattern_score, pattern_reasons = detect_patterns(df)
        trend_score, trend_reasons = score_trend_momentum(df)
        volume_score, volume_reasons = score_volume(df)
        total_score = pattern_score + trend_score + volume_score

        if total_score <= 0:
            continue

        ltp = round(float(df["close"].iloc[-1]), 2)

        all_results.append({
            "symbol": symbol,
            "exchange": "NSE",
            "ltp": ltp,
            "score": round(total_score, 1),
            "summary": plain_summary(pattern_score, trend_score, volume_score, total_score),
            "reasons": pattern_reasons + trend_reasons + volume_reasons,
            "category_scores": {
                "pattern": round(pattern_score, 1),
                "trend_momentum": round(trend_score, 1),
                "volume_smart_money": round(volume_score, 1),
            },
            "is_penny": ltp < PENNY_THRESHOLD,
        })

        if i % 50 == 0:
            print(f"Progress: {i}/{total} scanned, {len(all_results)} scored so far")

    except Exception as e:
        errors += 1
        if errors <= 20:
            print(f"Skipping {symbol}: {e}")

print(f"\nScan complete. {len(all_results)} stocks scored positively. {errors} errors/skips.")

nifty_section = [r for r in all_results if not r["is_penny"]]
penny_section = [r for r in all_results if r["is_penny"]]

nifty_section.sort(key=lambda x: x["score"], reverse=True)
penny_section.sort(key=lambda x: x["score"], reverse=True)

nifty_section = nifty_section[:TOP_N_PER_SECTION]
penny_section = penny_section[:TOP_N_PER_SECTION]

for rank, r in enumerate(nifty_section, start=1):
    r["rank"] = rank
for rank, r in enumerate(penny_section, start=1):
    r["rank"] = rank

output = {
    "generated_at": datetime.now().isoformat(),
    "universe_size": total,
    "penny_threshold": PENNY_THRESHOLD,
    "nifty500_stocks": nifty_section,
    "penny_stocks": penny_section,
}

with open("results.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"\n✅ Wrote results.json — {len(nifty_section)} regular stocks, {len(penny_section)} penny stocks.")
