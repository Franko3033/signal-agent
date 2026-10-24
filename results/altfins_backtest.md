# altFINS signallari backtesti — MEXC narxlarida

Davr: **2026-08-22 — 2026-10-21** (60 kun). altFINS signallari: 223380 → filtrdan keyin 16844. Kredit sarfi: 631.

Tushib qolganlar: MEXC hajmi kam — 10879, MEXC'da yo'q / ma'lumot kam — 2410, ma'lumot yetarli emas — 35

R'da, komissiya hisobga olingan. RAW = signaldan keyin darhol kirish, CONFIRM = 5M tasdiq bilan (agent kabi).

## TP = 2R

### Umumiy

| Variant | Savdo | Win | O'rtacha | Jami | Profit factor | Ketma-ket yutqiziq | Maks. pasayish |
|---|---|---|---|---|---|---|---|
| RAW, barcha soatlar | 3520 | 33% | -0.15R | -518.6R | 0.81 | 58 | 607.0R |
| RAW, sessiya oynalari | 427 | 26% | -0.35R | -147.6R | 0.59 | 19 | 160.2R |
| **RAW, agent rejimi** (sessiyada 1 ta) | 41 | 20% | -0.56R | -23.0R | 0.39 | 8 | 23.0R |
| CONFIRM, barcha soatlar | 1625 | 34% | -0.10R | -169.5R | 0.86 | 33 | 199.4R |
| CONFIRM, sessiya oynalari | 202 | 32% | -0.17R | -33.8R | 0.78 | 16 | 51.5R |
| **CONFIRM, agent rejimi** (sessiyada 1 ta) | 38 | 42% | +0.16R | +6.1R | 1.25 | 3 | 3.9R |

### Signal oilasi bo'yicha (CONFIRM)

| Variant | Savdo | Win | O'rtacha | Jami | Profit factor | Ketma-ket yutqiziq | Maks. pasayish |
|---|---|---|---|---|---|---|---|
| CONFIRM — Breakout | 348 | 31% | -0.18R | -63.1R | 0.76 | 11 | 67.0R |
| CONFIRM — MA kesishuvi | 460 | 32% | -0.17R | -76.5R | 0.79 | 15 | 87.5R |
| CONFIRM — Supportdan qaytish | 817 | 36% | -0.04R | -29.9R | 0.95 | 28 | 108.5R |

## TP = 3R

### Umumiy

| Variant | Savdo | Win | O'rtacha | Jami | Profit factor | Ketma-ket yutqiziq | Maks. pasayish |
|---|---|---|---|---|---|---|---|
| RAW, barcha soatlar | 3520 | 25% | -0.17R | -604.6R | 0.80 | 58 | 736.0R |
| RAW, sessiya oynalari | 427 | 18% | -0.44R | -187.6R | 0.53 | 39 | 199.9R |
| **RAW, agent rejimi** (sessiyada 1 ta) | 41 | 17% | -0.46R | -19.0R | 0.51 | 8 | 20.7R |
| CONFIRM, barcha soatlar | 1625 | 24% | -0.17R | -278.7R | 0.80 | 61 | 327.9R |
| CONFIRM, sessiya oynalari | 202 | 23% | -0.22R | -44.4R | 0.75 | 26 | 76.4R |
| **CONFIRM, agent rejimi** (sessiyada 1 ta) | 38 | 34% | +0.20R | +7.5R | 1.27 | 4 | 5.4R |

### Signal oilasi bo'yicha (CONFIRM)

| Variant | Savdo | Win | O'rtacha | Jami | Profit factor | Ketma-ket yutqiziq | Maks. pasayish |
|---|---|---|---|---|---|---|---|
| CONFIRM — Breakout | 348 | 21% | -0.29R | -101.2R | 0.67 | 38 | 109.6R |
| CONFIRM — MA kesishuvi | 460 | 23% | -0.23R | -106.5R | 0.74 | 24 | 128.3R |
| CONFIRM — Supportdan qaytish | 817 | 26% | -0.09R | -71.0R | 0.90 | 53 | 141.1R |

## Signal turi bo'yicha (CONFIRM, TP 2R, kamida 20 savdo)

| Signal | Savdo | Win | Jami |
|---|---|---|---|
| MA_RIBBON | 165 | 40% | +13.7R |
| SUPPORT_RESISTANCE_BREAKOUT | 53 | 40% | +5.3R |
| PRICE_SMA_10_20 | 33 | 36% | -1.9R |
| PRICE_SMA_30_50 | 22 | 36% | -2.3R |
| SUPPORT_RESISTANCE_APPROACHING | 290 | 38% | -7.5R |
| PRICE_EMA_9_12 | 39 | 31% | -8.5R |
| PULLBACK_UP_DOWN_TREND | 320 | 35% | -10.2R |
| PULLBACK_UP_DOWN_TREND_1W | 145 | 35% | -10.3R |
| PRICE_EMA_50_100 | 29 | 21% | -16.1R |
| PRICE_SMA_5_10 | 71 | 21% | -35.5R |
| NEW_LOCAL_HIGH_LOW_5_PERIODS | 264 | 31% | -47.6R |

## Eslatmalar
- Agentdagi baho (3/5) va 'resistance juda yaqin' filtrlari bu yerda qo'llanmagan — sof signal sifati o'lchandi.
- Kapitalizatsiya signal paytidagi altFINS qiymati bo'yicha; MEXC hajmi signaldan oldingi 24 soat bo'yicha.
- Bir 5M sham ichida SL va TP birga bo'lsa — SL hisoblangan (konservativ).
