#!/usr/bin/env python3
"""
15M momentum strategiyasi backtesti (MEXC spot).

Qoidalar:
  1. 15M: sham so'nggi tasdiqlangan swing high'dan yuqorida yopiladi (BOS), bullish sham.
  2. Hajm: yorish shami hajmi 20 shamlik o'rtachadan >= 1.5x.
  3. Xavf filtri: narx 1H EMA200 dan 3% dan ortiq past emas.
  4. 5M tasdiq: yorishdan keyingi 2 soat ichida bullish 5M sham darajadan va oldingi
     5M maksimumdan yuqorida yopiladi -> Entry. SL ostiga tushsa — bekor.
  5. SL: yorishdan oldingi oraliqdagi eng past nuqta - 0.2*ATR (0.3..3 ATR oralig'ida bo'lmasa — o'tkaziladi).
     TP: 2R va 3R variantlari. 72 soatdan keyin bozor narxida yopiladi.
  6. Komissiya: har tomonga 0.05% (jami 0.1%).

Variantlar: 4H filtrisiz / 4H filtri bilan (4H: narx > EMA50 va EMA20 > EMA50),
            barcha soatlar / faqat agent kuzatadigan sessiya oynalari (London, New York).

Natija: results/backtest.md va results/trades.csv
"""
import os
import sys
import csv
import time
import math
import argparse
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from collections import defaultdict

import requests

MEXC = "https://api.mexc.com"
TZ_LOCAL = ZoneInfo("Asia/Tashkent")
HERE = os.path.dirname(os.path.abspath(__file__))
STABLES = {"USDC", "FDUSD", "TUSD", "DAI", "USDD", "USDE", "PYUSD", "BUSD", "USDP", "EUR", "EURC",
           "USD1", "USDT", "RLUSD", "XAUT", "PAXG", "USDS", "FRAX", "GUSD", "SUSD", "LUSD", "AEUR"}
LEVERAGED = ("3L", "3S", "5L", "5S", "2L", "2S", "4L", "4S", "UP", "DOWN", "BULL", "BEAR")

FEE = 0.0005            # har tomonga
VOL_MULT = 1.5
CONFIRM_BARS = 24       # 5M sham = 2 soat
MAX_HOLD_H = 72


# ---------------------------------------------------------------- ma'lumot
def get(path, params, tries=5):
    for i in range(tries):
        try:
            r = requests.get(MEXC + path, params=params, timeout=20)
            if r.status_code == 429:
                time.sleep(2 + i * 2)
                continue
            if r.status_code == 400:
                return None
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            time.sleep(1 + i)
    return None


def universe(n, min_vol):
    data = get("/api/v3/ticker/24hr", {}) or []
    rows = []
    for t in data:
        s = t.get("symbol", "")
        if not s.endswith("USDT"):
            continue
        base = s[:-4]
        if base in STABLES or any(base.endswith(x) for x in LEVERAGED):
            continue
        try:
            qv = float(t.get("quoteVolume") or 0)
        except ValueError:
            continue
        if qv >= min_vol:
            rows.append((qv, s))
    rows.sort(reverse=True)
    return [s for _, s in rows[:n]]


def klines(symbol, interval, start_ms, end_ms):
    step = {"5m": 300_000, "15m": 900_000}[interval]
    out, cur = [], start_ms
    while cur < end_ms:
        d = get("/api/v3/klines", {"symbol": symbol, "interval": interval,
                                    "startTime": cur, "endTime": min(end_ms, cur + step * 1000), "limit": 1000})
        if not d:
            # ma'lumot yo'q oraliq — oldinga siljish
            cur += step * 1000
            continue
        for x in d:
            t = int(x[0])
            if not out or t > out[-1][0]:
                out.append((t, float(x[1]), float(x[2]), float(x[3]), float(x[4]), float(x[5])))
        nxt = int(d[-1][0]) + step
        cur = nxt if nxt > cur else cur + step * 1000
        time.sleep(0.05)
    return out


# ---------------------------------------------------------------- indikatorlar
def ema(vals, n):
    out = [None] * len(vals)
    if len(vals) < n:
        return out
    k = 2 / (n + 1)
    e = sum(vals[:n]) / n
    out[n - 1] = e
    for i in range(n, len(vals)):
        e = vals[i] * k + e * (1 - k)
        out[i] = e
    return out


def atr(c, n=14):
    out = [None] * len(c)
    trs = [c[0][2] - c[0][3]]
    for i in range(1, len(c)):
        trs.append(max(c[i][2] - c[i][3], abs(c[i][2] - c[i - 1][4]), abs(c[i][3] - c[i - 1][4])))
    if len(trs) < n:
        return out
    a = sum(trs[:n]) / n
    out[n - 1] = a
    for i in range(n, len(trs)):
        a = (a * (n - 1) + trs[i]) / n
        out[i] = a
    return out


def resample(c15, minutes):
    """15M -> 1H/4H; har bir katta sham uchun (yopilish_vaqti_ms, close)."""
    span = minutes * 60_000
    buckets = {}
    for t, o, h, l, cl, v in c15:
        b = t // span * span
        buckets[b] = cl  # oxirgi 15M close = katta sham close
    keys = sorted(buckets)
    return [(k + span, buckets[k]) for k in keys]


def htf_series(c15, minutes, periods):
    """Har bir 15M sham uchun shu paytda YOPILGAN oxirgi katta shamning EMA qiymatlari."""
    big = resample(c15, minutes)
    closes = [x[1] for x in big]
    emas = {p: ema(closes, p) for p in periods}
    res = [None] * len(c15)
    j = -1
    for i, row in enumerate(c15):
        close_time = row[0] + 900_000
        while j + 1 < len(big) and big[j + 1][0] <= close_time:
            j += 1
        if j >= 0:
            res[i] = {p: emas[p][j] for p in periods} | {"close": closes[j]}
    return res


# ---------------------------------------------------------------- sessiya oynalari
SESS = [(ZoneInfo("Europe/London"), 8), (ZoneInfo("America/New_York"), 8)]


def in_session(ms):
    """Agent kuzatadigan oyna: ochilishdan 30 daqiqa oldin + 2 soat (ish kunlari)."""
    dt = datetime.fromtimestamp(ms / 1000, timezone.utc)
    for tz, hour in SESS:
        loc = dt.astimezone(tz)
        if loc.weekday() >= 5:
            continue
        open_dt = loc.replace(hour=hour, minute=0, second=0, microsecond=0)
        if open_dt - timedelta(minutes=30) <= loc < open_dt + timedelta(minutes=90):
            return True
    return False


# ---------------------------------------------------------------- strategiya
def find_trades(symbol, c15, c5):
    if len(c15) < 400 or len(c5) < 400:
        return []
    closes = [x[4] for x in c15]
    vols = [x[5] for x in c15]
    a15 = atr(c15)
    h1 = htf_series(c15, 60, [200])
    h4 = htf_series(c15, 240, [20, 50])
    idx5 = {row[0]: i for i, row in enumerate(c5)}
    t5 = [r[0] for r in c5]

    trades = []
    busy_until = 0
    last_swing_high = None   # (index, price)
    k = 3
    for t in range(250, len(c15)):
        # yangi tasdiqlangan swing high: t-k indeksdagi sham, o'ngida k ta sham bor
        p = t - k
        win = c15[p - k:p + k + 1]
        if c15[p][2] == max(x[2] for x in win):
            last_swing_high = (p, c15[p][2])
        if last_swing_high is None or c15[t][0] < busy_until:
            continue
        sh_i, H = last_swing_high
        bar = c15[t]
        if not (bar[4] > H >= c15[t - 1][4] and bar[4] > bar[1]):
            continue
        avg_v = sum(vols[t - 20:t]) / 20 or 1e-12
        if bar[5] < VOL_MULT * avg_v:
            continue
        hv = h1[t]
        if not hv or hv[200] is None or bar[4] < hv[200] * 0.97:
            continue
        A = a15[t]
        if not A:
            continue
        sl = min(x[3] for x in c15[sh_i:t + 1]) - 0.2 * A
        f4 = h4[t]
        h4_ok = bool(f4 and f4[50] and f4[20] and f4["close"] > f4[50] and f4[20] > f4[50])

        # 5M tasdiq
        start_ms = bar[0] + 900_000
        j = idx5.get(start_ms)
        if j is None:
            # eng yaqin keyingi 5M sham
            import bisect
            j = bisect.bisect_left(t5, start_ms)
        entry = entry_ms = None
        for q in range(j, min(j + CONFIRM_BARS, len(c5))):
            b5 = c5[q]
            if b5[4] < sl:
                break
            if q > 0 and b5[4] > b5[1] and b5[4] > H and b5[4] > c5[q - 1][2]:
                entry, entry_ms, eq = b5[4], b5[0] + 300_000, q
                break
        if entry is None:
            continue
        risk = entry - sl
        if not (0.3 * A <= risk <= 3 * A):
            continue

        # chiqish simulyatsiyasi (5M bo'yicha, SL birinchi tekshiriladi — konservativ)
        res = {}
        for rr in (2, 3):
            tp = entry + rr * risk
            outcome, exit_ms = None, None
            limit_ms = entry_ms + MAX_HOLD_H * 3600_000
            for q in range(eq + 1, len(c5)):
                b5 = c5[q]
                if b5[0] >= limit_ms:
                    outcome, exit_ms = (b5[1] - entry) / risk, b5[0]
                    break
                if b5[3] <= sl:
                    outcome, exit_ms = -1.0, b5[0]
                    break
                if b5[2] >= tp:
                    outcome, exit_ms = float(rr), b5[0]
                    break
            if outcome is None:
                outcome, exit_ms = (c5[-1][4] - entry) / risk, c5[-1][0]
            fee_r = (2 * FEE * entry) / risk
            res[rr] = (outcome - fee_r, exit_ms)
        busy_until = max(res[2][1], res[3][1])
        trades.append({
            "symbol": symbol, "signal_time": datetime.fromtimestamp(bar[0] / 1000, TZ_LOCAL).strftime("%Y-%m-%d %H:%M"),
            "entry_ms": entry_ms, "entry": entry, "sl": sl, "risk_pct": risk / entry * 100,
            "h4_ok": h4_ok, "session": in_session(entry_ms),
            "r2": round(res[2][0], 3), "r3": round(res[3][0], 3),
        })
    return trades


# ---------------------------------------------------------------- statistika
def stats(rs):
    n = len(rs)
    if n == 0:
        return dict(n=0, win=0, avg=0, total=0, pf=0, streak=0, dd=0)
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    pf = (sum(wins) / -sum(losses)) if losses and sum(losses) < 0 else float("inf")
    streak = cur = 0
    eq = peak = dd = 0.0
    for r in rs:
        cur = cur + 1 if r <= 0 else 0
        streak = max(streak, cur)
        eq += r
        peak = max(peak, eq)
        dd = max(dd, peak - eq)
    return dict(n=n, win=len(wins) / n * 100, avg=sum(rs) / n, total=sum(rs), pf=pf, streak=streak, dd=dd)


def best_per_session(trades, key):
    """Agent rejimi: har sessiya oynasida birinchi tasdiqlangan signal (kuniga <= 2)."""
    picked, seen = [], set()
    for tr in sorted(trades, key=lambda x: x["entry_ms"]):
        if not tr["session"]:
            continue
        dt = datetime.fromtimestamp(tr["entry_ms"] / 1000, TZ_LOCAL)
        slot = (dt.date(), "AM" if dt.hour < 15 else "PM")
        if slot in seen:
            continue
        seen.add(slot)
        picked.append(tr)
    return picked


def fmt_row(name, s):
    pf = "∞" if s["pf"] == float("inf") else f"{s['pf']:.2f}"
    return (f"| {name} | {s['n']} | {s['win']:.0f}% | {s['avg']:+.2f}R | {s['total']:+.1f}R | {pf} | "
            f"{s['streak']} | {s['dd']:.1f}R |")


def report(trades, meta):
    L = [f"# 15M momentum backtest — MEXC spot", "",
         f"Davr: **{meta['start']} — {meta['end']}** ({meta['days']} kun), coinlar: **{meta['coins']}** "
         f"(MEXC 24s hajmi bo'yicha top, >= ${meta['min_vol']/1e6:.0f}M), ma'lumoti to'liq: {meta['ok']}", "",
         "Natijalar R'da (1R = SL gacha bo'lgan risk), komissiya hisobga olingan (0.1% aylanma).", ""]
    hdr = ["| Variant | Savdo | Win | O'rtacha | Jami | Profit factor | Ketma-ket yutqiziq | Maks. pasayish |",
           "|---|---|---|---|---|---|---|---|"]
    for rr in (2, 3):
        k = f"r{rr}"
        L += [f"## TP = {rr}R", ""] + hdr
        groups = [
            ("Barcha soatlar, 4H filtrisiz", [t for t in trades]),
            ("Barcha soatlar, 4H filtri bilan", [t for t in trades if t["h4_ok"]]),
            ("Sessiya oynalari, 4H filtrisiz", [t for t in trades if t["session"]]),
            ("Sessiya oynalari, 4H filtri bilan", [t for t in trades if t["session"] and t["h4_ok"]]),
            ("**Agent rejimi** (sessiyada 1 ta, 4H filtrisiz)", best_per_session(trades, k)),
            ("**Agent rejimi** (sessiyada 1 ta, 4H filtri bilan)", best_per_session([t for t in trades if t["h4_ok"]], k)),
        ]
        for name, g in groups:
            g = sorted(g, key=lambda x: x["entry_ms"])
            L.append(fmt_row(name, stats([t[k] for t in g])))
        L.append("")

    # oyma-oy (asosiy variant: barcha soatlar, 4H filtrisiz, TP 2R)
    L += ["## Oyma-oy (barcha soatlar, 4H filtrisiz, TP 2R)", "",
          "| Oy | Savdo | Win | Jami |", "|---|---|---|---|"]
    by_m = defaultdict(list)
    for t in sorted(trades, key=lambda x: x["entry_ms"]):
        by_m[t["signal_time"][:7]].append(t["r2"])
    for m, rs in sorted(by_m.items()):
        s = stats(rs)
        L.append(f"| {m} | {s['n']} | {s['win']:.0f}% | {s['total']:+.1f}R |")
    L += ["", "## Eslatmalar",
          "- Coinlar ro'yxati bugungi hajm bo'yicha tanlangan (survivorship bias bor: o'lib ketgan coinlar yo'q).",
          "- Bir 5M sham ichida ham SL, ham TP bo'lsa — SL hisoblangan (konservativ).",
          "- Bir coinda bir vaqtda faqat bitta savdo.",
          "- Kapitalizatsiya filtri tarixda qo'llanmagan (MEXC'da tarixiy kapitalizatsiya yo'q), o'rniga hajm filtri."]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--coins", type=int, default=150)
    ap.add_argument("--min-vol", type=float, default=2_000_000)
    a = ap.parse_args()

    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(days=a.days)
    warm = start - timedelta(days=12)  # EMA200 (1H) uchun isinish
    syms = universe(a.coins, a.min_vol)
    print(f"{len(syms)} ta coin, {start:%Y-%m-%d} — {end:%Y-%m-%d}", flush=True)

    all_trades, ok = [], 0
    for n, s in enumerate(syms, 1):
        try:
            c15 = klines(s, "15m", int(warm.timestamp() * 1000), int(end.timestamp() * 1000))
            c5 = klines(s, "5m", int(start.timestamp() * 1000), int(end.timestamp() * 1000))
            # signal faqat start'dan keyin
            tr = [t for t in find_trades(s, c15, c5) if t["entry_ms"] >= start.timestamp() * 1000]
            if len(c15) > 0.8 * (a.days + 12) * 96 and len(c5) > 0.8 * a.days * 288:
                ok += 1
            all_trades += tr
            print(f"[{n}/{len(syms)}] {s}: 15m={len(c15)} 5m={len(c5)} savdo={len(tr)}", flush=True)
        except Exception as e:
            print(f"[{n}/{len(syms)}] {s}: xato {e}", flush=True)

    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    with open(os.path.join(HERE, "results", "trades.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["symbol", "signal_time", "entry", "sl", "risk_pct", "h4_ok",
                                          "session", "r2", "r3"], extrasaction="ignore")
        w.writeheader()
        for t in sorted(all_trades, key=lambda x: x["entry_ms"]):
            w.writerow(t)
    meta = dict(start=f"{start:%Y-%m-%d}", end=f"{end:%Y-%m-%d}", days=a.days, coins=len(syms),
                min_vol=a.min_vol, ok=ok)
    txt = report(all_trades, meta)
    with open(os.path.join(HERE, "results", "backtest.md"), "w", encoding="utf-8") as f:
        f.write(txt)
    print(txt)


if __name__ == "__main__":
    main()
