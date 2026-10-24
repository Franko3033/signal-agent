#!/usr/bin/env python3
"""
altFINS signallari backtesti: tarixiy BULLISH (kuchli turlar) signallar -> MEXC narxlarida natija.

Har bir signal uchun ikki variant:
  RAW      — signaldan keyingi birinchi yopilgan 5M sham narxida kirish.
  CONFIRM  — agent kabi: 2 soat ichida bullish 5M sham signal paytidagi 1 soatlik maksimumdan
             yuqorida yopilsa kirish; undan oldin SL ostiga tushsa — bekor.
SL: signal oldidan 20 ta 15M sham ichidagi eng past nuqta - 0.2*ATR (0.3..3 ATR bo'lmasa — 1.5*ATR).
TP: 2R / 3R, 72 soatda bozor narxida yopish, komissiya 0.1%.
Filtrlar: kapitalizatsiya >= 50 mln $, MEXC 24s hajmi >= 500 ming $, bir coinda 4 soat ichida 1 signal.
Natija: results/altfins_backtest.md, results/altfins_trades.csv
"""
import os
import sys
import csv
import time
import bisect
import argparse
from datetime import datetime, timedelta, timezone
from collections import defaultdict

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import backtest as bt                                   # noqa: E402
from agent import is_strong_signal, signal_family, parse_number, FAMILY_NAMES  # noqa: E402

ALT = "https://altfins.com"
KEY = os.environ.get("ALTFINS_API_KEY", "")
H = {"x-api-key": KEY, "Content-Type": "application/json", "Accept": "application/json"}


def credits():
    try:
        r = requests.get(f"{ALT}/api/v2/public/monthly-available-permits", headers=H, timeout=20)
        return float(str(r.text).strip().strip('"'))
    except Exception:
        return None


def signal_keys():
    r = requests.get(f"{ALT}/api/v2/public/signals-feed/signal-keys", headers=H, timeout=30)
    r.raise_for_status()
    d = r.json()
    if isinstance(d, dict):
        d = d.get("content") or d.get("data") or d.get("keys") or list(d.values())
    out = []
    for x in d:
        if isinstance(x, str):
            out.append(x)
        elif isinstance(x, dict):
            out.append(x.get("signalKey") or x.get("key") or x.get("name") or "")
    return [k for k in out if k]


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def fetch(keys, start, end, guard):
    items, cur = [], start
    size = 500
    step = timedelta(hours=6)
    while cur < end:
        nxt = min(cur + step, end)
        body = {"signalDirection": "BULLISH", "fromDate": iso(cur), "toDate": iso(nxt)}
        if keys:
            body["signals"] = keys
        for page in range(200):
            r = requests.post(f"{ALT}/api/v2/public/signals-feed/search-requests",
                              params={"page": page, "size": size, "sort": "timestamp,asc"},
                              json=body, headers=H, timeout=40)
            if r.status_code == 429:
                time.sleep(5)
                continue
            if r.status_code == 400 and size > 100:
                size = 100
                continue
            if r.status_code != 200:
                print("altFINS xato", r.status_code, r.text[:200], flush=True)
                break
            d = r.json()
            chunk = d if isinstance(d, list) else (d.get("content") or [])
            items += chunk
            last = True if isinstance(d, list) else d.get("last", True)
            if not chunk or last:
                break
            time.sleep(2.1)  # 30 so'rov/daqiqa limiti
        time.sleep(2.1)
        if cur.hour == 0:
            c = credits()
            print(f"{cur:%Y-%m-%d}: jami {len(items)} signal, kredit qoldi {c}", flush=True)
            if c is not None and c < guard:
                print("Kredit chegarasiga yetildi — to'xtatildi", flush=True)
                break
        cur = nxt
    return items


def simulate(sig_ms, c15, c5, t15, t5):
    i15 = bisect.bisect_left(t15, sig_ms) - 1          # signal paytidagi oxirgi yopilgan 15M sham
    if i15 < 30:
        return None
    a = bt.atr(c15[max(0, i15 - 300):i15 + 1])[-1]
    if not a:
        return None
    # likvidlik: so'nggi 24 soat hajmi (USDT)
    vol24 = sum(x[4] * x[5] for x in c15[max(0, i15 - 95):i15 + 1])
    j = bisect.bisect_left(t5, sig_ms)
    if j < 13 or j >= len(c5) - 2:
        return None
    hi1h = max(x[2] for x in c5[j - 12:j])
    sl0 = min(x[3] for x in c15[i15 - 19:i15 + 1]) - 0.2 * a
    out = {"vol24": vol24}
    for mode in ("raw", "confirm"):
        entry = eq = None
        if mode == "raw":
            entry, eq = c5[j][4], j
        else:
            for q in range(j, min(j + 24, len(c5))):
                b = c5[q]
                if b[4] < sl0:
                    break
                if b[4] > b[1] and b[4] > hi1h:
                    entry, eq = b[4], q
                    break
        if entry is None:
            out[mode] = None
            continue
        sl = sl0
        if not (0.3 * a <= entry - sl <= 3 * a):
            sl = entry - 1.5 * a
        risk = entry - sl
        res = {}
        for rr in (2, 3):
            tp = entry + rr * risk
            limit = c5[eq][0] + 72 * 3600_000
            r_ = None
            for q in range(eq + 1, len(c5)):
                b = c5[q]
                if b[0] >= limit:
                    r_ = (b[1] - entry) / risk
                    break
                if b[3] <= sl:
                    r_ = -1.0
                    break
                if b[2] >= tp:
                    r_ = float(rr)
                    break
            if r_ is None:
                r_ = (c5[-1][4] - entry) / risk
            res[rr] = round(r_ - 2 * bt.FEE * entry / risk, 3)
        out[mode] = {"entry": entry, "entry_ms": c5[eq][0] + 300_000, "r2": res[2], "r3": res[3]}
    return out


def table(rows, title):
    L = [f"### {title}", "",
         "| Variant | Savdo | Win | O'rtacha | Jami | Profit factor | Ketma-ket yutqiziq | Maks. pasayish |",
         "|---|---|---|---|---|---|---|---|"]
    for name, rs in rows:
        L.append(bt.fmt_row(name, bt.stats(rs)))
    return L + [""]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    ap.add_argument("--guard", type=float, default=50_000, help="kredit shu qiymatdan kam qolsa to'xtash")
    a = ap.parse_args()
    if not KEY:
        sys.exit("ALTFINS_API_KEY yo'q")

    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(days=3)
    start = end - timedelta(days=a.days)
    c0 = credits()
    keys = [k for k in signal_keys() if is_strong_signal(k)]
    print(f"Kredit: {c0}. Kuchli signal turlari: {len(keys)}", flush=True)
    items = fetch(keys, start, end, a.guard)
    c1 = credits()
    print(f"altFINS: {len(items)} signal olindi, kredit sarfi: {None if c0 is None or c1 is None else c0 - c1}", flush=True)

    # filtrlash va takrorlarni olib tashlash
    sigs, last_seen = [], {}
    for it in sorted(items, key=lambda x: x.get("timestamp", "")):
        key = str(it.get("signalKey", ""))
        if not is_strong_signal(key):
            continue
        cap = parse_number(it.get("marketCap"))
        if cap is None or cap < 50_000_000:
            continue
        sym = str(it.get("symbol", "")).upper()
        try:
            ts = datetime.fromisoformat(str(it["timestamp"]).replace("Z", "+00:00"))
        except Exception:
            continue
        ms = int(ts.timestamp() * 1000)
        if sym in last_seen and ms - last_seen[sym] < 4 * 3600_000:
            continue
        last_seen[sym] = ms
        sigs.append({"symbol": sym, "ms": ms, "key": key, "family": signal_family(key)})
    print(f"Filtrdan keyin: {len(sigs)} signal, {len({s['symbol'] for s in sigs})} coin", flush=True)

    by_sym = defaultdict(list)
    for s in sigs:
        by_sym[s["symbol"]].append(s)
    trades, skipped = [], defaultdict(int)
    warm = start - timedelta(days=4)
    fin = end + timedelta(days=3)
    for n, (sym, lst) in enumerate(sorted(by_sym.items()), 1):
        pair = sym + "USDT"
        c15 = bt.klines(pair, "15m", int(warm.timestamp() * 1000), int(fin.timestamp() * 1000))
        if len(c15) < 500:
            skipped["MEXC'da yo'q / ma'lumot kam"] += len(lst)
            continue
        c5 = bt.klines(pair, "5m", int(start.timestamp() * 1000), int(fin.timestamp() * 1000))
        t15 = [x[0] + 900_000 for x in c15]   # yopilish vaqtlari
        t5 = [x[0] for x in c5]
        for s in lst:
            r = simulate(s["ms"], c15, c5, t15, t5)
            if r is None:
                skipped["ma'lumot yetarli emas"] += 1
                continue
            if r["vol24"] < 500_000:
                skipped["MEXC hajmi kam"] += 1
                continue
            for mode in ("raw", "confirm"):
                if r[mode]:
                    trades.append({"symbol": sym, "mode": mode, "signal": s["key"].replace("SIGNALS_SUMMARY_", ""),
                                   "family": s["family"], "entry_ms": r[mode]["entry_ms"],
                                   "time": datetime.fromtimestamp(s["ms"] / 1000, bt.TZ_LOCAL).strftime("%Y-%m-%d %H:%M"),
                                   "session": bt.in_session(r[mode]["entry_ms"]),
                                   "r2": r[mode]["r2"], "r3": r[mode]["r3"]})
        print(f"[{n}/{len(by_sym)}] {pair}: signal={len(lst)} 15m={len(c15)} 5m={len(c5)}", flush=True)

    os.makedirs(os.path.join(HERE, "results"), exist_ok=True)
    with open(os.path.join(HERE, "results", "altfins_trades.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["time", "symbol", "signal", "family", "mode", "session", "r2", "r3"],
                           extrasaction="ignore")
        w.writeheader()
        for t in sorted(trades, key=lambda x: x["entry_ms"]):
            w.writerow(t)

    L = ["# altFINS signallari backtesti — MEXC narxlarida", "",
         f"Davr: **{start:%Y-%m-%d} — {end:%Y-%m-%d}** ({a.days} kun). "
         f"altFINS signallari: {len(items)} → filtrdan keyin {len(sigs)}. Kredit sarfi: "
         f"{None if c0 is None or c1 is None else round(c0 - c1)}.", "",
         "Tushib qolganlar: " + ", ".join(f"{k} — {v}" for k, v in skipped.items()), "",
         "R'da, komissiya hisobga olingan. RAW = signaldan keyin darhol kirish, "
         "CONFIRM = 5M tasdiq bilan (agent kabi).", ""]
    for rr in (2, 3):
        k = f"r{rr}"
        L.append(f"## TP = {rr}R\n")
        rows = []
        for mode, mname in (("raw", "RAW"), ("confirm", "CONFIRM")):
            g = sorted([t for t in trades if t["mode"] == mode], key=lambda x: x["entry_ms"])
            rows.append((f"{mname}, barcha soatlar", [t[k] for t in g]))
            rows.append((f"{mname}, sessiya oynalari", [t[k] for t in g if t["session"]]))
            ag = bt.best_per_session(g, k)
            rows.append((f"**{mname}, agent rejimi** (sessiyada 1 ta)", [t[k] for t in ag]))
        L += table(rows, "Umumiy")
        fam_rows = []
        for fam in sorted({t["family"] for t in trades}):
            g = sorted([t for t in trades if t["mode"] == "confirm" and t["family"] == fam], key=lambda x: x["entry_ms"])
            fam_rows.append((f"CONFIRM — {FAMILY_NAMES.get(fam, fam)}", [t[k] for t in g]))
        L += table(fam_rows, "Signal oilasi bo'yicha (CONFIRM)")
    # eng ko'p uchragan signal turlari (CONFIRM, 2R)
    by_sig = defaultdict(list)
    for t in trades:
        if t["mode"] == "confirm":
            by_sig[t["signal"]].append(t["r2"])
    L += ["## Signal turi bo'yicha (CONFIRM, TP 2R, kamida 20 savdo)", "",
          "| Signal | Savdo | Win | Jami |", "|---|---|---|---|"]
    for sname, rs in sorted(by_sig.items(), key=lambda x: -sum(x[1])):
        if len(rs) >= 20:
            s = bt.stats(rs)
            L.append(f"| {sname} | {s['n']} | {s['win']:.0f}% | {s['total']:+.1f}R |")
    L += ["", "## Eslatmalar",
          "- Agentdagi baho (3/5) va 'resistance juda yaqin' filtrlari bu yerda qo'llanmagan — sof signal sifati o'lchandi.",
          "- Kapitalizatsiya signal paytidagi altFINS qiymati bo'yicha; MEXC hajmi signaldan oldingi 24 soat bo'yicha.",
          "- Bir 5M sham ichida SL va TP birga bo'lsa — SL hisoblangan (konservativ)."]
    txt = "\n".join(L) + "\n"
    with open(os.path.join(HERE, "results", "altfins_backtest.md"), "w", encoding="utf-8") as f:
        f.write(txt)
    print(txt)


if __name__ == "__main__":
    main()
