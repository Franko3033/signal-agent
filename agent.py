#!/usr/bin/env python3
"""
Kripto signal agenti
altFINS Signals Feed (BULLISH) -> MEXC 15M texnik tahlil -> Entry / SL / TP -> Telegram
London va New York sessiyalari ochilishidan oldin kuniga 2 marta ishlaydi.

Ishga tushirish:
    python agent.py                 # doimiy rejim (jadval bo'yicha)
    python agent.py --once          # hozir bir marta ishlatish
    python agent.py --once --dry-run   # Telegram'ga yubormasdan ekranga chiqarish
    python agent.py --test-telegram # Telegram ulanishini tekshirish
    python agent.py --get-chat-id   # chat ID ni aniqlash
    python agent.py --credits       # altFINS kredit qoldig'i
    python agent.py --once --debug  # altFINS javobini altfins_raw.json ga saqlash
"""
import os
import sys
import json
import time
import argparse
import re
import logging
from datetime import datetime, timedelta, timezone, time as dtime
from zoneinfo import ZoneInfo

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ALTFINS_BASE = "https://altfins.com"
MEXC_HOST = "https://api.mexc.com"
MEXC_INTERVALS = {"5m": "5m", "15m": "15m", "1h": "60m"}  # MEXC 1 soatni "60m" deb yozadi
TZ_LOCAL = ZoneInfo("Asia/Tashkent")
SESSIONS = [
    # (nomi, bayroq, vaqt zonasi, ochilish soati)
    ("London", "🇬🇧", ZoneInfo("Europe/London"), dtime(8, 0)),
    ("New York", "🇺🇸", ZoneInfo("America/New_York"), dtime(8, 0)),
]

log = logging.getLogger("agent")


# ----------------------------------------------------------------- sozlamalar
def load_env(path):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def cfg(name, default=None, cast=str):
    v = os.environ.get(name, "")
    if v == "":
        return default
    if cast is bool:
        return v.lower() in ("1", "true", "yes", "ha")
    return cast(v)


# ----------------------------------------------------------------- altFINS
def altfins_headers():
    key = cfg("ALTFINS_API_KEY")
    if not key:
        sys.exit("config.env faylida ALTFINS_API_KEY yo'q")
    return {"x-api-key": key, "Content-Type": "application/json", "Accept": "application/json"}


def iso_utc(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def fetch_signals(lookback_min, debug=False):
    """So'nggi lookback_min daqiqadagi BULLISH signallarni oladi."""
    now = datetime.now(timezone.utc)
    body = {
        "signalDirection": "BULLISH",
        "fromDate": iso_utc(now - timedelta(minutes=lookback_min)),
        "toDate": iso_utc(now),
    }
    items, raw_pages = [], []
    for page in range(20):
        r = requests.post(
            f"{ALTFINS_BASE}/api/v2/public/signals-feed/search-requests",
            params={"page": page, "size": 100, "sort": "timestamp,desc"},
            json=body, headers=altfins_headers(), timeout=30,
        )
        if r.status_code != 200:
            raise RuntimeError(f"altFINS xatosi {r.status_code}: {r.text[:300]}")
        data = r.json()
        raw_pages.append(data)
        if isinstance(data, list):
            items.extend(data)
            break
        chunk = data.get("content") or data.get("data") or data.get("items") or []
        items.extend(chunk)
        if not chunk or data.get("last", True):
            break
    if debug:
        log.info("altFINS namunasi: %s", json.dumps(items[:2], ensure_ascii=False)[:1500])
        with open(os.path.join(HERE, "altfins_raw.json"), "w", encoding="utf-8") as f:
            json.dump(raw_pages, f, ensure_ascii=False, indent=2)
        log.info("altFINS xom javobi altfins_raw.json ga saqlandi")
    return items


def _field(item, *names):
    for n in names:
        if n in item and item[n] not in (None, ""):
            return item[n]
    return None


def signal_interval(item):
    for k, v in item.items():
        kl = k.lower()
        if "interval" in kl or "timeframe" in kl or "period" in kl:
            return str(v)
    return None


def parse_number(v):
    """'13,185,653' yoki 1.3e7 -> float; bo'lmasa None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).replace(",", "").replace(" ", "").replace("$", ""))
    except ValueError:
        return None


def signal_level(item):
    """Signalda ko'rsatilgan narx darajasi (breakout/support/resistance), bo'lsa."""
    for k, v in item.items():
        kl = k.lower()
        if any(w in kl for w in ("level", "breakout", "resistance", "support", "trigger", "target")):
            try:
                f = float(v)
                if f > 0:
                    return f
            except (TypeError, ValueError):
                pass
    return None


# altFINS signal turlari -> tasdiq qoidasi oilasi (tartib muhim: birinchi mos kelgani olinadi)
SIGNAL_FAMILIES = [
    ("MACD", ["MACD"]),
    ("OSC", ["RSI", "STOCH", "WILLIAMS", "OVERSOLD", "CCI", "ULTIMATE"]),
    ("CANDLE", ["HAMMER", "ENGULFING", "MORNING", "PIERCING", "TWEEZER", "THREE_WHITE", "DOJI",
                "HARAMI", "KICKER", "THREE_INSIDE", "THREE_OUTSIDE", "ABANDONED", "DRAGONFLY",
                "THREE_LINE_STRIKE", "SPINNING", "CONSECUTIVE"]),
    ("SUPPORT", ["SUPPORT", "BOTTOM", "PULLBACK", "INVERSE_HEAD", "RETRACEMENT", "BUTTERFLY",
                 "GARTLEY", "ABCD", "DRIVE", "EXTENSION"]),
    ("BREAKOUT", ["BREAKOUT", "RESISTANCE", "TRIANGLE", "FLAG", "PENNANT", "WEDGE", "RECTANGLE",
                  "CHANNEL", "NEW_LOCAL_HIGH", "ATH", "TRADING_RANGE", "BIG_MOVEMENT", "GAINERS",
                  "UNUSUAL_VOLUME", "RVOL", "TR_ATR", "BOLLBAND", "EMERGING"]),
    ("MA_CROSS", ["EMA", "SMA", "MA_RIBBON"]),
    ("TREND", ["TREND", "MOMENTUM", "OBV", "POWER"]),
]
FAMILY_NAMES = {
    "MACD": "MACD kesishuvi", "OSC": "Osillyator qaytishi", "CANDLE": "Sham figurasi",
    "SUPPORT": "Supportdan qaytish", "BREAKOUT": "Breakout", "MA_CROSS": "MA kesishuvi",
    "TREND": "Trend davomi",
}


def signal_family(key):
    k = str(key).upper()
    for fam, words in SIGNAL_FAMILIES:
        if any(w in k for w in words):
            return fam
    return "BREAKOUT"


# Kuchli signal turlari (oq ro'yxat) va zaif/shovqinli turlar (qora ro'yxat).
# Qora ro'yxat birinchi tekshiriladi.
WEAK_SIGNALS = ["POWER", "WILLIAMS", "STOCH", "RSI", "CCI", "ULTIMATE", "OVERSOLD", "OVERBOUGHT",
                "MACD", "TOP_GAINERS", "TOP_LOSERS", "BIG_MOVEMENT", "UNUSUAL_VOLUME", "RVOL",
                "TR_ATR", "FUNDAMENTALS", "ATH", "CONSECUTIVE", "BOLLBAND", "OBV", "MOMENTUM"]
STRONG_SIGNALS = [
    # breakout va resistance/support
    "BREAKOUT", "HORIZONTAL_RESISTANCE", "HORIZONTAL_SUPPORT", "SUPPORT_RESISTANCE",
    "NEW_LOCAL_HIGH", "TRADING_RANGE", "PULLBACK",
    # chart figuralari
    "TRIANGLE", "FLAG", "PENNANT", "WEDGE", "RECTANGLE", "CHANNEL_UP", "DOUBLE_BOTTOM",
    "TRIPLE_BOTTOM", "INVERSE_HEAD", "EMERGING_PATTERNS", "ABCD", "GARTLEY", "BUTTERFLY",
    "DRIVE", "POINT_RETRACEMENT", "POINT_EXTENSION",
    # o'rtacha chiziqlar kesishuvi
    "EMA_", "SMA_", "MA_RIBBON",
]


def is_strong_signal(key):
    k = str(key).upper()
    if any(w in k for w in WEAK_SIGNALS):
        return False
    return any(w in k for w in STRONG_SIGNALS)


def group_signals(items, only_15m=True):
    """Signallarni coin bo'yicha guruhlaydi:
    {SYMBOL: [{"key", "name", "family", "level"}, ...]}"""
    out = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        direction = str(_field(it, "direction", "signalDirection") or "BULLISH").upper()
        if "BEAR" in direction:
            continue
        iv = signal_interval(it)
        if only_15m and iv is not None and "15" not in iv:
            continue
        sym = _field(it, "symbol", "symbolName", "coin")
        if isinstance(sym, dict):
            sym = sym.get("symbol") or sym.get("name")
        if not sym:
            continue
        sym = str(sym).upper().replace("/", "").replace("-", "")
        if sym.endswith("USDT"):
            sym = sym[:-4]
        key = str(_field(it, "signalKey", "signal", "key") or _field(it, "signalName", "name") or "SIGNAL")
        if cfg("STRONG_ONLY", True, bool) and not is_strong_signal(key):
            continue
        min_cap = cfg("MIN_MARKET_CAP", 50_000_000, float)
        if min_cap > 0:
            cap = parse_number(_field(it, "marketCap", "market_cap", "MARKET_CAP"))
            if cap is None or cap < min_cap:
                continue
        name = _field(it, "signalName", "name") or key
        name = str(name).replace("SIGNALS_SUMMARY_", "").replace("_", " ").title()
        out.setdefault(sym, [])
        if all(s["key"] != key for s in out[sym]):
            out[sym].append({"key": key, "name": name, "family": signal_family(key),
                             "level": signal_level(it)})
    return out


def altfins_credits():
    r = requests.get(f"{ALTFINS_BASE}/api/v2/public/monthly-available-permits",
                     headers=altfins_headers(), timeout=20)
    return r.status_code, r.text


# ----------------------------------------------------------------- MEXC
def klines(pair, interval, limit):
    """MEXC spot shamlari. Juftlik MEXC spot'da bo'lmasa None qaytaradi."""
    now_ms = int(time.time() * 1000)
    params = {"symbol": pair, "interval": MEXC_INTERVALS.get(interval, interval), "limit": limit}
    for attempt in range(3):
        try:
            r = requests.get(f"{MEXC_HOST}/api/v3/klines", params=params, timeout=15)
            if r.status_code == 400:
                return None  # bunday juftlik MEXC spot'da yo'q
            if r.status_code == 429:
                time.sleep(2 * (attempt + 1))
                continue
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, list):
                return None
            rows = [dict(t=x[0], o=float(x[1]), h=float(x[2]), l=float(x[3]),
                         c=float(x[4]), v=float(x[5]), ct=x[6]) for x in data]
            # yopilmagan (joriy) shamni olib tashlash
            step = {"5m": 5, "15m": 15, "1h": 60}.get(interval, 15) * 60_000
            if rows and (rows[-1]["ct"] > now_ms or rows[-1]["t"] + step > now_ms):
                rows = rows[:-1]
            return rows
        except requests.RequestException as e:
            log.warning("MEXC %s (urinish %d): %s", pair, attempt + 1, e)
            time.sleep(1)
    return None


# ----------------------------------------------------------------- indikatorlar
def ema(vals, n):
    if len(vals) < n:
        return [None] * len(vals)
    out = [None] * (n - 1)
    prev = sum(vals[:n]) / n
    out.append(prev)
    k = 2 / (n + 1)
    for v in vals[n:]:
        prev = v * k + prev * (1 - k)
        out.append(prev)
    return out


def rsi_wilder(closes, n=14):
    if len(closes) <= n:
        return [None] * len(closes)
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    out = [None] * n

    def val(g, l):
        return 100.0 if l == 0 else 100 - 100 / (1 + g / l)
    out.append(val(ag, al))
    for i in range(n, len(gains)):
        ag = (ag * (n - 1) + gains[i]) / n
        al = (al * (n - 1) + losses[i]) / n
        out.append(val(ag, al))
    return out


def macd_hist(closes, fast=12, slow=26, sig=9):
    ef, es = ema(closes, fast), ema(closes, slow)
    line = [a - b for a, b in zip(ef, es) if a is not None and b is not None]
    s = ema(line, sig)
    return [m - x for m, x in zip(line, s) if x is not None]


def atr_wilder(c, n=14):
    trs = []
    for i in range(1, len(c)):
        trs.append(max(c[i]["h"] - c[i]["l"], abs(c[i]["h"] - c[i - 1]["c"]), abs(c[i]["l"] - c[i - 1]["c"])))
    if len(trs) < n:
        return None
    a = sum(trs[:n]) / n
    for tr in trs[n:]:
        a = (a * (n - 1) + tr) / n
    return a


def swings(c, k=3):
    """Swing high/low (fraktal) nuqtalari."""
    highs, lows = [], []
    for i in range(k, len(c) - k):
        win = c[i - k:i + k + 1]
        if c[i]["h"] == max(x["h"] for x in win):
            highs.append(c[i]["h"])
        if c[i]["l"] == min(x["l"] for x in win):
            lows.append(c[i]["l"])
    return highs, lows


# ----------------------------------------------------------------- tahlil
def analyze(sym, c15, c1h, min_rr=2.0, entry=None):
    """Natija: dict (signal) yoki None + sabab."""
    if not c15 or len(c15) < 220 or not c1h or len(c1h) < 210:
        return None, "ma'lumot yetarli emas"
    closes = [x["c"] for x in c15]
    price = entry if entry else closes[-1]
    e20, e50, e200 = ema(closes, 20)[-1], ema(closes, 50)[-1], ema(closes, 200)[-1]
    h_closes = [x["c"] for x in c1h]
    h50, h200 = ema(h_closes, 50)[-1], ema(h_closes, 200)[-1]
    rsi = rsi_wilder(closes)[-1]
    hist = macd_hist(closes)
    atr = atr_wilder(c15)
    vols = [x["v"] for x in c15]
    base_vol = sum(vols[-23:-3]) / 20 or 1e-12
    vol_ratio = (sum(vols[-3:]) / 3) / base_vol

    checks = [
        ("1H trend ↑", h_closes[-1] > h50 > h200),
        ("15M trend ↑", price > e50 and e20 > e50),
        (f"RSI {rsi:.0f}", 45 <= rsi <= 70),
        ("MACD ↑", hist[-1] > 0 and hist[-1] >= hist[-2]),
        (f"Hajm x{vol_ratio:.1f}", vol_ratio >= 1.2),
    ]
    score = sum(1 for _, ok in checks if ok)
    if rsi > cfg("MAX_RSI", 80, float):
        return None, f"RSI {rsi:.0f} — o'ta qizib ketgan"

    # --- SL: oxirgi support (swing low) ostida
    highs, lows = swings(c15[-150:])
    supports = [l for l in lows if l < price - 0.3 * atr]
    sl_note = "support ostida"
    if supports:
        sl = max(supports) - 0.25 * atr
    else:
        sl = price - 1.5 * atr
        sl_note = "1.5×ATR"
    risk = price - sl
    if not (0.5 * atr <= risk <= 3 * atr):
        sl = price - 1.5 * atr
        sl_note = "1.5×ATR"
        risk = price - sl
    if risk <= 0:
        return None, "SL hisoblanmadi"

    # --- TP: TP1 = 1:min_rr, TP2 = keyingi resistance yoki 1:3
    tp1 = price + min_rr * risk
    # Resistance: 1H swing high'lar (asosiy) + 15M kuchli swing high'lar (k=5)
    h_highs, _ = swings(c1h[-120:], k=3)
    m_highs, _ = swings(c15[-250:], k=5)
    resistances = sorted(h for h in h_highs + m_highs if h > price + 0.3 * atr)
    warn = None
    if resistances:
        rr_first = (resistances[0] - price) / risk
        if rr_first < 1.0:
            return None, f"resistance juda yaqin ({fmt(resistances[0])}, RR 1:{rr_first:.1f})"
        if resistances[0] < tp1:
            warn = f"⚠️ TP1 dan oldin resistance: {fmt(resistances[0])} (1:{rr_first:.1f})"
    above = [r for r in resistances if r > tp1 + 0.2 * atr]
    if above:
        tp2, tp2_note = above[0], "resistance"
    else:
        tp2, tp2_note = price + 3 * risk, "R asosida"
    if tp2 <= tp1:
        tp2, tp2_note = price + 3 * risk, "R asosida"

    return {
        "symbol": sym, "price": price, "sl": sl, "sl_note": sl_note,
        "tp1": tp1, "tp2": tp2, "tp2_note": tp2_note,
        "rr2": (tp2 - price) / risk, "score": score, "checks": checks, "atr": atr,
        "warn": warn,
    }, "ok"


# ----------------------------------------------------------------- formatlash
def fmt(p):
    if p >= 1000:
        d = 2
    elif p >= 1:
        d = 4
    elif p >= 0.01:
        d = 5
    else:
        d = 8
    return f"{p:,.{d}f}".replace(",", " ")


def pct(a, b):
    return (b - a) / a * 100


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_signal(s, signal_names):
    p = s["price"]
    checks = "\n".join(("✅ " if ok else "▫️ ") + esc(name) for name, ok in s["checks"])
    names = ", ".join(esc(n) for n in signal_names[:4])
    return (
        f"🟢 <b>BUY — {esc(s['symbol'])}/USDT</b> (15M · MEXC spot)\n"
        f"📡 altFINS: {names}\n"
        f"⭐ Baho: <b>{s['score']}/5</b>\n"
        + (f"✅ 5M tasdiq: {esc(s['confirm'])}\n" if s.get("confirm") else "")
        + "\n"
        f"💵 Entry: <code>{fmt(p)}</code>\n"
        f"🛑 SL: <code>{fmt(s['sl'])}</code> ({pct(p, s['sl']):.2f}%) — {s['sl_note']}\n"
        f"🎯 TP1: <code>{fmt(s['tp1'])}</code> (+{pct(p, s['tp1']):.2f}%, 1:2)\n"
        f"🎯 TP2: <code>{fmt(s['tp2'])}</code> (+{pct(p, s['tp2']):.2f}%, 1:{s['rr2']:.1f}, {s['tp2_note']})\n\n"
        f"{checks}\n\n"
        + (f"{esc(s['warn'])}\n\n" if s.get("warn") else "")
        + f"<i>Moliyaviy maslahat emas. Kirishdan oldin grafikni o'zingiz tekshiring.</i>"
    )


# ----------------------------------------------------------------- Telegram
def tg_discover_chat(token):
    """Chat ID berilmagan bo'lsa: botga /start yozgan shaxsiy chatni topadi va eslab qoladi."""
    cache = os.path.join(HERE, "chat_id.txt")
    try:
        with open(cache, encoding="utf-8") as f:
            cid = f.read().strip()
            if cid:
                return cid
    except OSError:
        pass
    try:
        me = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=20).json()
        if not me.get("ok"):
            log.error("Telegram token noto'g'ri: %s", me.get("description"))
            return None
        log.info("Bot: @%s", me["result"].get("username"))
        wh = requests.get(f"https://api.telegram.org/bot{token}/getWebhookInfo", timeout=20).json()
        if wh.get("result", {}).get("url"):
            log.info("Botda webhook bor edi — o'chirilmoqda")
            requests.get(f"https://api.telegram.org/bot{token}/deleteWebhook", timeout=20)
        r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20).json()
        log.info("Botga kelgan xabarlar soni: %d", len(r.get("result", [])))
    except requests.RequestException as e:
        log.error("Telegram getUpdates xatosi: %s", e)
        return None
    for u in reversed(r.get("result", [])):
        ch = (u.get("message") or u.get("my_chat_member") or {}).get("chat") or {}
        if ch.get("type") == "private":
            cid = str(ch["id"])
            with open(cache, "w", encoding="utf-8") as f:
                f.write(cid)
            log.info("Telegram chat topildi: %s", ch.get("first_name") or ch.get("username"))
            return cid
    log.error("Chat topilmadi: Telegram'da botingizni ochib, Start tugmasini bosing")
    return None


def tg_send(text):
    token, chat = cfg("TELEGRAM_BOT_TOKEN"), cfg("TELEGRAM_CHAT_ID")
    if not token:
        sys.exit("TELEGRAM_BOT_TOKEN yo'q")
    if not chat:
        chat = tg_discover_chat(token)
        if not chat:
            return False
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      json={"chat_id": chat, "text": text, "parse_mode": "HTML",
                            "disable_web_page_preview": True}, timeout=20)
    if r.status_code != 200:
        log.error("Telegram xatosi %s: %s", r.status_code, r.text[:200])
    return r.status_code == 200


def tg_get_chat_id():
    token = cfg("TELEGRAM_BOT_TOKEN")
    if not token:
        sys.exit("config.env faylida TELEGRAM_BOT_TOKEN yo'q")
    r = requests.get(f"https://api.telegram.org/bot{token}/getUpdates", timeout=20).json()
    chats = {}
    for u in r.get("result", []):
        m = u.get("message") or u.get("channel_post") or {}
        ch = m.get("chat")
        if ch:
            chats[ch["id"]] = ch.get("title") or ch.get("username") or ch.get("first_name")
    if not chats:
        print("Hech narsa topilmadi. Telegram'da botingizga biror xabar (masalan /start) yozing va qayta urinib ko'ring.")
    for cid, name in chats.items():
        print(f"TELEGRAM_CHAT_ID={cid}    ({name})")


# ----------------------------------------------------------------- holat (takror yubormaslik)
STATE_FILE = os.path.join(HERE, "state.json")


def load_state():
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {"sent": {}}


def save_state(st):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=2)




# ----------------------------------------------------------------- 5M tasdiq qoidalari
def _ma_periods(key):
    nums = [int(n) for n in re.findall(r"\d+", str(key)) if int(n) >= 5]
    if len(nums) >= 2:
        return nums[0], nums[1]
    return 12, 50


def watch_context(c5, c15, sig):
    """Kuzatuv boshlanganda qoidalar uchun darajalarni eslab qoladi."""
    return {
        "hi12": max(x["h"] for x in c5[-12:]),          # so'nggi 1 soatlik 5M maksimum
        "sig_high": c15[-1]["h"],                       # signal bergan 15M sham maksimumi
        "level": sig.get("level"),
    }


def check_rule(sig, ctx, c5, c15):
    """Bitta altFINS signali uchun 5M tasdiq. Qaytaradi: tavsif (str) yoki None."""
    fam = sig["family"]
    last, prev = c5[-1], c5[-2]
    closes5 = [x["c"] for x in c5]
    bullish = last["c"] > last["o"]
    vols = [x["v"] for x in c5]
    avg_v = sum(vols[-21:-1]) / 20 or 1e-12
    vr = last["v"] / avg_v
    e20_5 = ema(closes5, 20)[-1]
    t = datetime.fromtimestamp(last["t"] / 1000, TZ_LOCAL).strftime("%H:%M")

    if fam == "BREAKOUT":
        trig = ctx["level"] or ctx["hi12"]
        if last["c"] > trig and bullish and vr >= 1.5:
            return f"{t} dagi 5M sham {fmt(trig)} darajadan yuqorida yopildi, hajm x{vr:.1f}"
    elif fam == "CANDLE":
        trig = ctx["sig_high"]
        if last["c"] > trig and bullish:
            return f"{t} dagi 5M sham figura maksimumi {fmt(trig)} dan yuqorida yopildi"
    elif fam == "MACD":
        line = [a - b for a, b in zip(ema(closes5, 12), ema(closes5, 26)) if a is not None and b is not None]
        sigl = ema(line, 9)
        h = [m - x for m, x in zip(line, sigl) if x is not None]
        if len(h) >= 2 and h[-1] > 0 and h[-2] > 0 and h[-1] > h[-2] and last["c"] > e20_5:
            return f"{t} da 5M MACD signal chizig'idan yuqorida, gistogramma o'smoqda"
    elif fam == "OSC":
        r = rsi_wilder(closes5)
        if r[-1] is not None and r[-1] > 30 and r[-1] > r[-2] and last["c"] > prev["h"] and bullish:
            return f"{t} da 5M RSI {r[-1]:.0f} ga ko'tarildi, sham oldingi maksimumdan yuqori yopildi"
    elif fam == "MA_CROSS":
        f, s = _ma_periods(sig["key"])
        cl15 = [x["c"] for x in c15]
        ef, es = ema(cl15, f)[-1], ema(cl15, s)[-1]
        if ef and es and ef > es and last["c"] > ef and last["c"] > prev["h"] and bullish:
            return f"15M MA{f} > MA{s} saqlanmoqda, {t} dagi 5M sham MA{f} ({fmt(ef)}) va oldingi maksimumdan yuqori yopildi"
    elif fam == "SUPPORT":
        hi6 = max(x["h"] for x in c5[-7:-1])
        if last["c"] > hi6 and bullish:
            return f"{t} dagi 5M sham supportdan qaytib, so'nggi 30 daqiqa maksimumi {fmt(hi6)} dan yuqori yopildi"
    elif fam == "TREND":
        if last["c"] > e20_5 and last["c"] > ctx["hi12"] and bullish:
            return f"{t} dagi 5M sham EMA20 va 1 soatlik maksimum {fmt(ctx['hi12'])} dan yuqori yopildi"
    return None


# ----------------------------------------------------------------- sessiya: signal olish + 2 soat kuzatish
def sleep_until(dt):
    while True:
        left = (dt - datetime.now(timezone.utc)).total_seconds()
        if left <= 0:
            return
        time.sleep(min(30, left))


def next_5m_close(now):
    m = (now.minute // 5 + 1) * 5
    base = now.replace(second=0, microsecond=0, minute=0)
    return base + timedelta(minutes=m, seconds=15)


def send(msg, dry_run):
    if dry_run:
        print("-" * 40)
        print(msg)
    else:
        tg_send(msg)
        time.sleep(0.4)


def add_candidates(watch, done, st, lookback, min_rr, min_score, debug):
    items = fetch_signals(lookback, debug=debug)
    groups = group_signals(items, only_15m=cfg("ONLY_15M", True, bool))
    added = []
    for sym, sigs in groups.items():
        if sym in watch:
            for sg in sigs:  # yangi signal turi qo'shilsa
                if all(x["key"] != sg["key"] for x in watch[sym]["sigs"]):
                    sg["ctx"] = watch[sym]["sigs"][0]["ctx"]
                    watch[sym]["sigs"].append(sg)
            continue
        if sym in done or sym in st["sent"]:
            continue
        pair = sym + "USDT"
        c15 = klines(pair, "15m", 300)
        if c15 is None:
            done[sym] = "MEXC spot'da yo'q"
            continue
        min_vol = cfg("MIN_MEXC_VOLUME", 2_000_000, float)
        vol24 = sum(x["c"] * x["v"] for x in c15[-96:])  # so'nggi 24 soat (96 × 15M), USDT
        if vol24 < min_vol:
            done[sym] = f"MEXC 24s hajmi kam (${vol24:,.0f})"
            continue
        c1h = klines(pair, "1h", 250)
        pre, why = analyze(sym, c15, c1h, min_rr=min_rr)
        if pre is None:
            done[sym] = why
            continue
        if pre["score"] < min_score:
            done[sym] = f"baho {pre['score']}/5"
            continue
        c5 = klines(pair, "5m", 80)
        if not c5 or len(c5) < 40:
            done[sym] = "5M ma'lumot yo'q"
            continue
        for sg in sigs:
            sg["ctx"] = watch_context(c5, c15, sg)
        watch[sym] = {"sigs": sigs, "sl": pre["sl"], "last_ct": c5[-1]["t"]}
        added.append(sym)
        time.sleep(0.15)
    log.info("altFINS: %d signal, %d coin, %d tasi kuzatuvga olindi", len(items), len(groups), len(added))
    return added


def run_session(label, minutes, dry_run=False, debug=False):
    lookback = cfg("LOOKBACK_MINUTES", 120, int)
    min_score = cfg("MIN_SCORE", 3, int)
    max_signals = cfg("MAX_SIGNALS", 1, int)
    min_rr = cfg("MIN_RR", 2.0, float)
    refresh_min = cfg("REFRESH_MINUTES", 30, int)
    dedup_h = cfg("DEDUP_HOURS", 12, float)

    start = datetime.now(timezone.utc)
    end = start + timedelta(minutes=minutes)
    st = load_state()
    st["sent"] = {k: v for k, v in st.get("sent", {}).items() if v > time.time() - dedup_h * 3600}
    watch, done, confirmed = {}, {}, []

    log.info("Sessiya boshlandi: %s (%s daqiqa)", label, minutes)
    added = add_candidates(watch, done, st, lookback, min_rr, max(0, min_score - 1), debug)
    last_refresh = datetime.now(timezone.utc)

    if cfg("SEND_WATCHLIST", False, bool):
        lines = [f"<b>{esc(label)}</b>",
                 f"🕒 {datetime.now(TZ_LOCAL):%d.%m.%Y %H:%M} (Toshkent)",
                 f"👀 Kuzatuvga olindi: <b>{len(watch)} ta coin</b>"]
        for sym in list(watch)[:15]:
            fams = ", ".join(sorted({FAMILY_NAMES[s['family']] for s in watch[sym]['sigs']}))
            lines.append(f"• {esc(sym)} — {esc(fams)}")
        end_local = end.astimezone(TZ_LOCAL)
        lines.append(f"\n5M tasdiq {end_local:%H:%M} gacha kutiladi. Tasdiqlanganlari alohida keladi.")
        if not watch:
            lines.append("Hozircha mos altFINS signali yo'q; har 30 daqiqada qayta tekshiraman.")
        send("\n".join(lines), dry_run)

    while datetime.now(timezone.utc) < end and len(confirmed) < max_signals:
        nxt = next_5m_close(datetime.now(timezone.utc))
        if nxt > end:
            break
        sleep_until(nxt)

        if (datetime.now(timezone.utc) - last_refresh).total_seconds() >= refresh_min * 60:
            try:
                new = add_candidates(watch, done, st, refresh_min + 15, min_rr, max(0, min_score - 1), False)
                if new and cfg("SEND_WATCHLIST", False, bool):
                    send("👀 Kuzatuvga qo'shildi: " + ", ".join(esc(s) for s in new), dry_run)
            except Exception as e:
                log.warning("altFINS yangilash xatosi: %s", e)
            last_refresh = datetime.now(timezone.utc)

        hits = []
        for sym in list(watch):
            w = watch[sym]
            pair = sym + "USDT"
            c5 = klines(pair, "5m", 80)
            if not c5 or c5[-1]["t"] == w["last_ct"]:
                continue
            w["last_ct"] = c5[-1]["t"]
            if c5[-1]["c"] < w["sl"]:
                done[sym] = "narx SL ostiga tushdi — bekor"
                del watch[sym]
                continue
            c15 = klines(pair, "15m", 300)
            hit = None
            for sg in w["sigs"]:
                txt = check_rule(sg, sg["ctx"], c5, c15)
                if txt:
                    hit = (sg, txt)
                    break
            if not hit:
                continue
            c1h = klines(pair, "1h", 250)
            res, why = analyze(sym, c15, c1h, min_rr=min_rr, entry=c5[-1]["c"])
            del watch[sym]
            if res is None:
                done[sym] = f"tasdiq bor, lekin {why}"
                continue
            if res["score"] < min_score:
                done[sym] = f"tasdiq bor, lekin baho {res['score']}/5"
                continue
            res["confirm"] = f"{FAMILY_NAMES[hit[0]['family']]} — {hit[1]}"
            res["names"] = [x["name"] for x in w["sigs"]]
            # reyting: baho > altFINS signallari soni > TP2 gacha RR
            res["rank"] = res["score"] * 10 + min(len(w["sigs"]), 3) * 3 + min(res["rr2"], 5)
            hits.append(res)

        hits.sort(key=lambda r: r["rank"], reverse=True)
        slots = max_signals - len(confirmed)
        for res in hits[:slots]:
            send(format_signal(res, res["names"]), dry_run)
            confirmed.append(res["symbol"])
            st["sent"][res["symbol"]] = time.time()
        for res in hits[slots:]:
            done[res["symbol"]] = "tasdiq bor, lekin kuchliroq coin tanlandi"
        if hits and not dry_run:
            save_state(st)

    for sym in watch:
        done[sym] = "2 soat ichida tasdiq bo'lmadi"
    if not confirmed and cfg("SEND_EMPTY_REPORT", True, bool):
        send(f"🏁 {esc(label.split(' (')[0])}: 2 soat ichida 5M tasdiqli BUY setup bo'lmadi. "
             f"Bu sessiyada signal yo'q.", dry_run)
    for sym, why in done.items():
        log.info("  %s: %s", sym, why)
    log.info("Sessiya tugadi: %d ta tasdiqlandi", len(confirmed))


# ----------------------------------------------------------------- jadval
def upcoming_runs(now_utc, minutes_before, skip_weekends, include_recent_min=0):
    runs = []
    for name, flag, tz, open_t in SESSIONS:
        today = now_utc.astimezone(tz).date()
        for k in range(-1, 4):
            d = today + timedelta(days=k)
            if skip_weekends and d.weekday() >= 5:
                continue
            open_dt = datetime.combine(d, open_t, tzinfo=tz)
            run_dt = open_dt - timedelta(minutes=minutes_before)
            if run_dt > now_utc - timedelta(minutes=include_recent_min):
                local_open = open_dt.astimezone(TZ_LOCAL)
                label = f"{flag} {name} sessiyasi (ochilish {local_open:%H:%M})"
                runs.append((run_dt.astimezone(timezone.utc), label))
    runs.sort(key=lambda x: x[0])
    return runs


def run_forever(dry_run=False):
    mb = cfg("MINUTES_BEFORE_SESSION", 30, int)
    watch_min = cfg("WATCH_MINUTES", 120, int)
    skip_we = cfg("SKIP_WEEKENDS", True, bool)
    while True:
        run_dt, label = upcoming_runs(datetime.now(timezone.utc), mb, skip_we)[0]
        log.info("Keyingi sessiya: %s — %s", run_dt.astimezone(TZ_LOCAL).strftime("%d.%m %H:%M"), label)
        sleep_until(run_dt)
        try:
            run_session(label, watch_min, dry_run=dry_run)
        except Exception as e:
            log.exception("Xato: %s", e)
            if not dry_run:
                try:
                    tg_send(f"⚠️ Agent xatosi: {esc(e)}")
                except Exception:
                    pass
        time.sleep(5)


def run_ci(dry_run=False):
    """GitHub Actions uchun: yaqin sessiya bo'lsa ishlaydi, bo'lmasa chiqib ketadi."""
    mb = cfg("MINUTES_BEFORE_SESSION", 30, int)
    watch_min = cfg("WATCH_MINUTES", 120, int)
    now = datetime.now(timezone.utc)
    for run_dt, label in upcoming_runs(now, mb, cfg("SKIP_WEEKENDS", True, bool), include_recent_min=45):
        delta = (run_dt - now).total_seconds() / 60
        if -45 <= delta <= 35:
            st = load_state()
            key = run_dt.strftime("%Y-%m-%d ") + label.split(" (")[0]
            if key in st.get("sessions", {}):
                log.info("Bu sessiya allaqachon ishlangan: %s — chiqildi", key)
                return
            st.setdefault("sessions", {})[key] = time.time()
            st["sessions"] = {k: v for k, v in st["sessions"].items() if v > time.time() - 7 * 86400}
            save_state(st)
            sleep_until(run_dt)
            remaining = watch_min - max(0, (datetime.now(timezone.utc) - run_dt).total_seconds() / 60)
            run_session(label, int(remaining), dry_run=dry_run)
            return
    log.info("Hozir sessiya vaqti emas — chiqildi")


# ----------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="altFINS → MEXC 5M tasdiq → Telegram signal agenti")
    ap.add_argument("--once", action="store_true", help="hozir sessiya boshlash")
    ap.add_argument("--minutes", type=int, default=None, help="--once uchun kuzatuv davomiyligi (daqiqa)")
    ap.add_argument("--ci", action="store_true", help="GitHub Actions rejimi")
    ap.add_argument("--dry-run", action="store_true", help="Telegram'ga yubormasdan ekranga chiqarish")
    ap.add_argument("--debug", action="store_true", help="altFINS javobini faylga saqlash")
    ap.add_argument("--test-telegram", action="store_true")
    ap.add_argument("--get-chat-id", action="store_true")
    ap.add_argument("--credits", action="store_true")
    ap.add_argument("--schedule", action="store_true", help="keyingi sessiya vaqtlari")
    a = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S",
                        handlers=[logging.StreamHandler(),
                                  logging.FileHandler(os.path.join(HERE, "agent.log"), encoding="utf-8")])
    load_env(os.path.join(HERE, "config.env"))

    if a.get_chat_id:
        tg_get_chat_id()
    elif a.test_telegram:
        ok = tg_send("✅ Signal agenti ulandi! Sinov kuzatuvi boshlandi.")
        print("Yuborildi ✅" if ok else "Yuborilmadi ❌")
    elif a.credits:
        print(*altfins_credits())
    elif a.schedule:
        for run_dt, label in upcoming_runs(datetime.now(timezone.utc),
                                           cfg("MINUTES_BEFORE_SESSION", 30, int),
                                           cfg("SKIP_WEEKENDS", True, bool))[:6]:
            print(run_dt.astimezone(TZ_LOCAL).strftime("%a %d.%m %H:%M"), "—", label)
    elif a.ci:
        run_ci(dry_run=a.dry_run)
    elif a.once:
        run_session("Qo'lda ishga tushirildi", a.minutes or cfg("WATCH_MINUTES", 120, int),
                    dry_run=a.dry_run, debug=a.debug)
    else:
        run_forever(dry_run=a.dry_run)


if __name__ == "__main__":
    main()
