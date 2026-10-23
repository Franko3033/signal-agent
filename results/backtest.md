# 15M momentum backtest — MEXC spot

Davr: **2026-07-25 — 2026-10-23** (90 kun), coinlar: **33** (MEXC 24s hajmi bo'yicha top, >= $2M), ma'lumoti to'liq: 27

Natijalar R'da (1R = SL gacha bo'lgan risk), komissiya hisobga olingan (0.1% aylanma).

## TP = 2R

| Variant | Savdo | Win | O'rtacha | Jami | Profit factor | Ketma-ket yutqiziq | Maks. pasayish |
|---|---|---|---|---|---|---|---|
| Barcha soatlar, 4H filtrisiz | 831 | 34% | -0.17R | -144.6R | 0.78 | 18 | 159.2R |
| Barcha soatlar, 4H filtri bilan | 455 | 33% | -0.15R | -70.2R | 0.80 | 18 | 80.2R |
| Sessiya oynalari, 4H filtrisiz | 137 | 35% | -0.07R | -9.4R | 0.91 | 14 | 19.1R |
| Sessiya oynalari, 4H filtri bilan | 70 | 33% | -0.11R | -7.6R | 0.85 | 11 | 14.2R |
| **Agent rejimi** (sessiyada 1 ta, 4H filtrisiz) | 75 | 32% | -0.16R | -11.8R | 0.79 | 10 | 14.8R |
| **Agent rejimi** (sessiyada 1 ta, 4H filtri bilan) | 47 | 34% | -0.08R | -3.5R | 0.90 | 7 | 9.7R |

## TP = 3R

| Variant | Savdo | Win | O'rtacha | Jami | Profit factor | Ketma-ket yutqiziq | Maks. pasayish |
|---|---|---|---|---|---|---|---|
| Barcha soatlar, 4H filtrisiz | 831 | 28% | -0.09R | -76.6R | 0.89 | 20 | 99.1R |
| Barcha soatlar, 4H filtri bilan | 455 | 25% | -0.14R | -62.0R | 0.84 | 18 | 88.7R |
| Sessiya oynalari, 4H filtrisiz | 137 | 28% | -0.03R | -3.7R | 0.97 | 16 | 27.0R |
| Sessiya oynalari, 4H filtri bilan | 70 | 26% | -0.07R | -4.6R | 0.92 | 11 | 20.5R |
| **Agent rejimi** (sessiyada 1 ta, 4H filtrisiz) | 75 | 25% | -0.13R | -10.0R | 0.84 | 13 | 20.6R |
| **Agent rejimi** (sessiyada 1 ta, 4H filtri bilan) | 47 | 30% | +0.09R | +4.5R | 1.12 | 8 | 12.7R |

## Oyma-oy (barcha soatlar, 4H filtrisiz, TP 2R)

| Oy | Savdo | Win | Jami |
|---|---|---|---|
| 2026-07 | 42 | 31% | -10.4R |
| 2026-08 | 325 | 34% | -45.5R |
| 2026-09 | 302 | 37% | -22.6R |
| 2026-10 | 162 | 27% | -66.1R |

## Eslatmalar
- Coinlar ro'yxati bugungi hajm bo'yicha tanlangan (survivorship bias bor: o'lib ketgan coinlar yo'q).
- Bir 5M sham ichida ham SL, ham TP bo'lsa — SL hisoblangan (konservativ).
- Bir coinda bir vaqtda faqat bitta savdo.
- Kapitalizatsiya filtri tarixda qo'llanmagan (MEXC'da tarixiy kapitalizatsiya yo'q), o'rniga hajm filtri.
