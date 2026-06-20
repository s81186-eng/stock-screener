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

LOOKBACK_DAYS = 300          # enough history for EMA200
MAX_STOCKS = 100              # keep small at first to avoid rate limits; raise later
SLEEP_BETWEEN_CALLS = 0.4    # seconds, stay under Kite's rate limit

# A small starter watchlist (liquid, well-known NSE stocks).
# Replace/expand this with a full Nifty 500 list once the pipeline works.
WATCHLIST = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN", "ITC",
    "LT", "AXISBANK", "KOTAKBANK", "BHARTIARTL", "HINDUNILVR", "MARUTI",
    "SUNPHARMA", "TATAMOTORS", "TATASTEEL", "WIPRO", "ADANIENT", "ADANIPORTS",
    "BAJFINANCE", "ASIANPAINT", "ULTRACEMCO", "NESTLEIND", "POWERGRID",
    "NTPC", "ONGC", "TITAN", "JSWSTEEL", "GRASIM", "HCLTECH",
]

# ---------- LOGIN ----------
kite = KiteConnect(api_key=KITE_API_KEY)
kite.set_access_token(os.environ["ACCESS_TOKEN"])

# ---------- GET INSTRUMENT TOKENS ----------
instruments = kite.instruments("NSE")
instruments_df = pd.DataFrame(instruments)
instruments_df = instruments_df[instruments_df["instrument_type"] == "EQ"]

symbol_to_token = {}
for symbol in WATCHLIST:
    match = instruments_df[instruments_df["tradingsymbol"] == symbol]
    if not match.empty:
        symbol_to_token[symbol] = int(match.iloc[0]["instrument_token"])

print(f"Resolved {len(symbol_to_token)} of {len(WATCHLIST)} symbols.")

# ---------- FETCH HISTORICAL DATA ----------
def fetch_candles(token):
    to_date = datetime.now()
    from_date = to_date - timedelta(days=LOOKBACK_DAYS)
    candles = kite.historical_data(token, from_date, to_date, "day")
    df = pd.DataFrame(candles)
    if df.empty:
        return None
    df = df.rename(columns={
        "date": "date", "open": "open", "high": "high",
        "low": "low", "close": "close", "volume": "volume"
    })
    return df


# ---------- CANDLESTICK PATTERN DETECTION (simplified) ----------
def detect_patterns(df):
    reasons = []
    pattern_score = 0
    last = df.iloc[-1]
    prev = df.iloc[-2]

    body = abs(last["close"] - last["open"])
    candle_range = last["high"] - last["low"]
    lower_wick = min(last["open"], last["close"]) - last["low"]
    upper_wick = last["high"] - max(last["open"], last["close"])

    # Hammer: small body, long lower wick, near recent low
    if candle_range > 0 and lower_wick > 2 * body and upper_wick < body:
        recent_low = df["low"].tail(20).min()
        if last["low"] <= recent_low * 1.03:
            pattern_score += 15
            reasons.append("Hammer candle near recent support")

    # Bullish engulfing
    if (prev["close"] < prev["open"] and last["close"] > last["open"]
            and last["close"] > prev["open"] and last["open"] < prev["close"]):
        pattern_score += 15
        reasons.append("Bullish engulfing pattern")

    # Volume-confirmed breakout: today's close above 20-day high, on above-average volume
    recent_high_20 = df["high"].tail(21).iloc[:-1].max()
    avg_vol_20 = df["volume"].tail(21).iloc[:-1].mean()
    if last["close"] > recent_high_20 and last["volume"] > 1.5 * avg_vol_20:
        pattern_score += 10
        reasons.append("Breakout above 20-day high on strong volume")

    return min(pattern_score, 40), reasons


# ---------- TREND & MOMENTUM ----------
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
        score += 8
        reasons.append("Price above EMA50")

    if not ema200.isna().iloc[-1] and last_close > ema200.iloc[-1]:
        score += 8
        reasons.append("Price above EMA200")

    last_rsi = rsi.iloc[-1]
    if 40 <= last_rsi <= 65:
        score += 6
        reasons.append(f"RSI in healthy range ({last_rsi:.0f})")
    elif 30 <= last_rsi < 40:
        score += 8
        reasons.append(f"RSI rebounding from oversold ({last_rsi:.0f})")

    macd_line = macd.macd()
    macd_signal = macd.macd_signal()
    if (macd_line.iloc[-2] < macd_signal.iloc[-2]
            and macd_line.iloc[-1] > macd_signal.iloc[-1]):
        score += 8
        reasons.append("MACD bullish crossover")

    last_adx = adx.iloc[-1]
    if last_adx > 25:
        score += 5
        reasons.append(f"Strong trend strength (ADX {last_adx:.0f})")

    return min(score, 30), reasons


# ---------- VOLUME / SMART MONEY ----------
def score_volume(df):
    reasons = []
    score = 0

    obv = OnBalanceVolumeIndicator(df["close"], df["volume"]).on_balance_volume()
    obv_change = obv.iloc[-1] - obv.iloc[-15]
    price_change = df["close"].iloc[-1] - df["close"].iloc[-15]

    if obv_change > 0 and price_change <= 0:
        score += 10
        reasons.append("OBV rising while price flat/down (possible accumulation)")
    elif obv_change > 0 and price_change > 0:
        score += 5
        reasons.append("OBV confirms upward price move")

    avg_vol_20 = df["volume"].tail(21).iloc[:-1].mean()
    last_vol = df["volume"].iloc[-1]
    if avg_vol_20 > 0 and last_vol > 2 * avg_vol_20:
        score += 10
        reasons.append(f"Unusual volume spike ({last_vol / avg_vol_20:.1f}x average)")

    return min(score, 20), reasons


# ---------- TECHNICAL SANITY FILTER ----------
def passes_sanity(df):
    if len(df) < 200:
        return False  # not enough history
    if df["volume"].tail(20).mean() < 10000:
        return False  # too illiquid
    last_close = df["close"].iloc[-1]
    prev_close = df["close"].iloc[-2]
    if prev_close > 0 and abs(last_close - prev_close) / prev_close > 0.20:
        return False  # extreme single-day gap, likely corporate action/data issue
    return True


# ---------- MAIN LOOP ----------
results = []

for symbol, token in symbol_to_token.items():
    try:
        df = fetch_candles(token)
        time.sleep(SLEEP_BETWEEN_CALLS)

        if df is None or not passes_sanity(df):
            continue

        pattern_score, pattern_reasons = detect_patterns(df)
        trend_score, trend_reasons = score_trend_momentum(df)
        volume_score, volume_reasons = score_volume(df)

        total_score = pattern_score + trend_score + volume_score
        all_reasons = pattern_reasons + trend_reasons + volume_reasons

        if total_score <= 0:
            continue

        results.append({
            "symbol": symbol,
            "exchange": "NSE",
            "ltp": round(float(df["close"].iloc[-1]), 2),
            "score": round(total_score, 1),
            "reasons": all_reasons,
            "category_scores": {
                "pattern": pattern_score,
                "trend_momentum": trend_score,
                "volume_smart_money": volume_score,
            }
        })
        print(f"{symbol}: score {total_score:.1f}")

    except Exception as e:
        print(f"Skipping {symbol} due to error: {e}")
        continue

# ---------- RANK & SAVE ----------
results.sort(key=lambda x: x["score"], reverse=True)
for i, r in enumerate(results, start=1):
    r["rank"] = i

output = {
    "generated_at": datetime.now().isoformat(),
    "stocks": results
}

with open("results.json", "w") as f:
    json.dump(output, f, indent=2)

print(f"\n✅ Wrote results.json with {len(results)} stocks.")
