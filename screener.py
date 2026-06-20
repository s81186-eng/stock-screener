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
SLEEP_BETWEEN_CALLS = 0.35
TOP_N = 30  # only publish the top N ranked stocks

# Nifty 500 watchlist (NSE tradingsymbols). Sourced from the Nifty 500 constituents list.
WATCHLIST = [
    "360ONE","3MINDIA","ABB","ACC","ACMESOLAR","AIAENG","APLAPOLLO","AUBANK","AWL","AADHARHFC",
    "AARTIIND","AAVAS","ABBOTINDIA","ACE","ADANIENSOL","ADANIENT","ADANIGREEN","ADANIPORTS","ADANIPOWER","ATGL",
    "ABCAPITAL","ABFRL","ABREL","ABSLAMC","AEGISLOG","AFCONS","AFFLE","AJANTPHARM","AKUMS","APLLTD",
    "ALIVUS","ALKEM","ALKYLAMINE","ALOKINDS","ARE&M","AMBER","AMBUJACEM","ANANDRATHI","ANANTRAJ","ANGELONE",
    "APARINDS","APOLLOHOSP","APOLLOTYRE","APTUS","ASAHIINDIA","ASHOKLEY","ASIANPAINT","ASTERDM","ASTRAZEN","ASTRAL",
    "ATUL","AUROPHARMA","AVANTIFEED","DMART","AXISBANK","BASF","BEML","BLS","BSE","BAJAJ-AUTO",
    "BAJFINANCE","BAJAJFINSV","BAJAJHLDNG","BALAMINES","BALKRISIND","BALRAMCHIN","BANDHANBNK","BANKBARODA","BANKINDIA","MAHABANK",
    "BATAINDIA","BAYERCROP","BERGEPAINT","BDL","BEL","BHARATFORG","BHEL","BPCL","BHARTIARTL","BHARTIHEXA",
    "BIKAJI","BIOCON","BSOFT","BLUEDART","BLUESTARCO","BBTC","BOSCHLTD","FIRSTCRY","BRIGADE","BRITANNIA",
    "MAPMYINDIA","CCL","CESC","CGPOWER","CRISIL","CAMPUS","CANFINHOME","CANBK","CAPLIPOINT","CGCL",
    "CARBORUNIV","CASTROLIND","CEATLTD","CENTRALBK","CDSL","CENTURYPLY","CERA","CHALET","CHAMBLFERT","CHENNPETRO",
    "CHOLAHLDNG","CHOLAFIN","CIPLA","CUB","CLEAN","COALINDIA","COCHINSHIP","COFORGE","COHANCE","COLPAL",
    "CAMS","CONCORDBIO","CONCOR","COROMANDEL","CRAFTSMAN","CREDITACC","CROMPTON","CUMMINSIND","CYIENT","DCMSHRIRAM",
    "DLF","DOMS","DABUR","DALBHARAT","DATAPATTNS","DEEPAKFERT","DEEPAKNTR","DELHIVERY","DEVYANI","DIVISLAB",
    "DIXON","LALPATHLAB","DRREDDY","EIDPARRY","EIHOTEL","EICHERMOT","ELECON","ELGIEQUIP","EMAMILTD","EMCURE",
    "ENDURANCE","ENGINERSIN","ERIS","ESCORTS","EXIDEIND","NYKAA","FEDERALBNK","FACT","FINCABLES","FINPIPE",
    "FSL","FIVESTAR","FORTIS","GAIL","GVT&D","GMRAIRPORT","GRSE","GICRE","GILLETTE","GLAND",
    "GLAXO","GLENMARK","MEDANTA","GODIGIT","GPIL","GODFRYPHLP","GODREJAGRO","GODREJCP","GODREJIND","GODREJPROP",
    "GRANULES","GRAPHITE","GRASIM","GESHIP","FLUOROCHEM","GUJGASLTD","GMDCLTD","GNFC","GPPL","GSFC",
    "GSPL","HEG","HBLENGINE","HCLTECH","HDFCAMC","HDFCBANK","HDFCLIFE","HFCL","HAPPSTMNDS","HAVELLS",
    "HEROMOTOCO","HSCL","HINDALCO","HAL","HINDCOPPER","HINDPETRO","HINDUNILVR","HINDZINC","POWERINDIA","HOMEFIRST",
    "HONASA","HONAUT","HUDCO","HYUNDAI","ICICIBANK","ICICIGI","ICICIPRULI","IDBI","IDFCFIRSTB","IFCI",
    "IIFL","INOXINDIA","IRB","IRCON","ITC","ITI","INDGN","INDIACEM","INDIAMART","INDIANB",
    "IEX","INDHOTEL","IOC","IOB","IRCTC","IRFC","IREDA","IGL","INDUSTOWER","INDUSINDBK",
    "NAUKRI","INFY","INOXWIND","INTELLECT","INDIGO","IGIL","IKS","IPCALAB","JBCHEPHARM","JKCEMENT",
    "JBMA","JKTYRE","JMFINANCIL","JSWENERGY","JSWHL","JSWINFRA","JSWSTEEL","JPPOWER","J&KBANK","JINDALSAW",
    "JSL","JINDALSTEL","JIOFIN","JUBLFOOD","JUBLINGREA","JUBLPHARMA","JWL","JUSTDIAL","JYOTHYLAB","JYOTICNC",
    "KPRMILL","KEI","KNRCON","KPITTECH","KAJARIACER","KPIL","KALYANKJIL","KANSAINER","KARURVYSYA","KAYNES",
    "KEC","KFINTECH","KIRLOSBROS","KIRLOSENG","KOTAKBANK","KIMS","LTF","LTTS","LICHSGFIN","LTFOODS",
    "LTIM","LT","LATENTVIEW","LAURUSLABS","LEMONTREE","LICI","LINDEINDIA","LLOYDSME","LUPIN","MMTC",
    "MRF","LODHA","MGL","MAHSEAMLES","M&MFIN","M&M","MANAPPURAM","MRPL","MANKIND","MARICO",
    "MARUTI","MASTEK","MFSL","MAXHEALTH","MAZDOCK","METROPOLIS","MINDACORP","MSUMI","MOTILALOFS","MPHASIS",
    "MCX","MUTHOOTFIN","NATCOPHARM","NBCC","NCC","NHPC","NLCINDIA","NMDC","NSLNISP","NTPCGREEN",
    "NTPC","NH","NATIONALUM","NAVA","NAVINFLUOR","NESTLEIND","NETWEB","NETWORK18","NEULANDLAB","NEWGEN",
    "NAM-INDIA","NIVABUPA","NUVAMA","NUVOCO","OBEROIRLTY","ONGC","OIL","OLAELEC","OLECTRA","PAYTM",
    "OFSS","POLICYBZR","PCBL","PGEL","PIIND","PNBHOUSING","PNCINFRA","PTCIL","PVRINOX","PAGEIND",
    "PATANJALI","PERSISTENT","PETRONET","PFIZER","PHOENIXLTD","PIDILITIND","PEL","PPLPHARMA","POLYMED","POLYCAB",
    "POONAWALLA","PFC","POWERGRID","PRAJIND","PREMIERENE","PRESTIGE","PNB","RRKABEL","RBLBANK","RECLTD",
    "RHIM","RITES","RADICO","RVNL","RAILTEL","RAINBOW","RKFORGE","RCF","RTNINDIA","RAYMONDLSL",
    "RAYMOND","REDINGTON","RELIANCE","RPOWER","ROUTE","SBFC","SBICARD","SBILIFE","SJVN","SKFINDIA",
    "SRF","SAGILITY","SAILIFE","MOTHERSON","SAPPHIRE","SARDAEN","SAREGAMA","SCHAEFFLER","SCHNEIDER","SHREECEM",
    "RENUKA","SHRIRAMFIN","SHYAMMETL","SIEMENS","SIGNATURE","SOBHA","SOLARINDS","SONACOMS","SONATSOFTW","STARHEALTH",
    "SBIN","SAIL","SWSOLAR","SUMICHEM","SPARC","SUNPHARMA","SUNTV","SUNDARMFIN","SUNDRMFAST","SUPREMEIND",
    "SUZLON","SWANENERGY","SWIGGY","SYNGENE","SYRMA","TBOTEK","TVSMOTOR","TANLA","TATACHEM","TATACOMM",
    "TCS","TATACONSUM","TATAELXSI","TATAINVEST","TATAMOTORS","TATAPOWER","TATASTEEL","TATATECH","TTML","TECHM",
    "TECHNOE","TEJASNET","NIACL","RAMCOCEM","THERMAX","TIMKEN","TITAGARH","TITAN","TORNTPHARM","TORNTPOWER",
    "TARIL","TRENT","TRIDENT","TRIVENI","TRITURBINE","TIINDIA","UCOBANK","UNOMINDA","UPL","UTIAMC",
    "ULTRACEMCO","UNIONBANK","UBL","UNITDSPR","USHAMART","VGUARD","DBREALTY","VTL","VBL","MANYAVAR",
    "VEDL","VIJAYA","VMM","IDEA","VOLTAS","WAAREEENER","WELCORP","WELSPUNLIV","WESTLIFE","WHIRLPOOL",
    "WIPRO","WOCKPHARMA","YESBANK","ZFCVINDIA","ZEEL","ZENTEC","ZENSARTECH","ZYDUSLIFE","ECLERX",
]

# ---------- LOGIN ----------
kite = KiteConnect(api_key=KITE_API_KEY)
session_data = kite.generate_session(REQUEST_TOKEN, api_secret=KITE_API_SECRET)
kite.set_access_token(session_data["access_token"])
print("Logged in as:", kite.profile()["user_name"])

# ---------- INSTRUMENT TOKENS ----------
instruments = kite.instruments("NSE")
instruments_df = pd.DataFrame(instruments)
instruments_df = instruments_df[instruments_df["instrument_type"] == "EQ"]

symbol_to_token = {}
for symbol in WATCHLIST:
    match = instruments_df[instruments_df["tradingsymbol"] == symbol]
    if not match.empty:
        symbol_to_token[symbol] = int(match.iloc[0]["instrument_token"])
print(f"Resolved {len(symbol_to_token)} of {len(WATCHLIST)} symbols.")


def fetch_candles(token):
    to_date = datetime.now()
    from_date = to_date - timedelta(days=LOOKBACK_DAYS)
    candles = kite.historical_data(token, from_date, to_date, "day")
    df = pd.DataFrame(candles)
    return None if df.empty else df


# ---------- PATTERNS (bullish add, bearish penalize) ----------
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

    # Hammer near support
    if candle_range > 0 and lower_wick > 2 * body and upper_wick < body:
        recent_low = df["low"].tail(20).min()
        if last["low"] <= recent_low * 1.03:
            score += 14
            reasons.append("Hammer candle near recent support (bullish reversal signal)")

    # Bullish engulfing
    if (prev["close"] < prev["open"] and last["close"] > last["open"]
            and last["close"] > prev["open"] and last["open"] < prev["close"]):
        score += 14
        reasons.append("Bullish engulfing pattern (buyers overwhelmed sellers)")

    # Morning star (3-candle bullish reversal)
    if (prev2["close"] < prev2["open"]
            and abs(prev["close"] - prev["open"]) < (prev2["high"] - prev2["low"]) * 0.3
            and last["close"] > last["open"]
            and last["close"] > (prev2["open"] + prev2["close"]) / 2):
        score += 16
        reasons.append("Morning star pattern (strong bullish reversal)")

    # Bearish engulfing (penalize)
    if (prev["close"] > prev["open"] and last["close"] < last["open"]
            and last["close"] < prev["open"] and last["open"] > prev["close"]):
        score -= 12
        reasons.append("Bearish engulfing pattern (warning sign)")

    # Shooting star (bearish reversal at top)
    if candle_range > 0 and upper_wick > 2 * body and lower_wick < body:
        recent_high = df["high"].tail(20).max()
        if last["high"] >= recent_high * 0.97:
            score -= 10
            reasons.append("Shooting star near recent high (bearish warning)")

    # Volume-confirmed breakout
    recent_high_20 = df["high"].tail(21).iloc[:-1].max()
    if last["close"] > recent_high_20 and avg_vol_20 > 0 and last["volume"] > 1.5 * avg_vol_20:
        score += 12
        reasons.append("Breakout above 20-day high on strong volume")

    # Proximity to support (within 5% of 60-day low) — opportunity zone
    support = df["low"].tail(60).min()
    if support > 0 and 0 < (last["close"] - support) / support < 0.05:
        score += 6
        reasons.append("Price near 60-day support level")

    # Near 60-day resistance — riskier
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
    if df["volume"].tail(20).mean() < 10000:
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
results = []
total = len(symbol_to_token)
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

        results.append({
            "symbol": symbol,
            "exchange": "NSE",
            "ltp": round(float(df["close"].iloc[-1]), 2),
            "score": round(total_score, 1),
            "summary": plain_summary(pattern_score, trend_score, volume_score, total_score),
            "reasons": pattern_reasons + trend_reasons + volume_reasons,
            "category_scores": {
                "pattern": round(pattern_score, 1),
                "trend_momentum": round(trend_score, 1),
                "volume_smart_money": round(volume_score, 1),
            }
        })
        if i % 25 == 0:
            print(f"Progress: {i}/{total}")
    except Exception as e:
        print(f"Skipping {symbol}: {e}")

results.sort(key=lambda x: x["score"], reverse=True)
results = results[:TOP_N]
for rank, r in enumerate(results, start=1):
    r["rank"] = rank

output = {
    "generated_at": datetime.now().isoformat(),
    "universe_size": total,
    "stocks": results,
}
with open("results.json", "w") as f:
    json.dump(output, f, indent=2)
print(f"\n✅ Wrote results.json with {len(results)} ranked stocks (from {total} scanned).")
