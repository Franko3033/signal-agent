# Kripto signal agenti (altFINS → MEXC 5M tasdiq → Telegram)

## Qanday ishlaydi

Har ish kuni ikki marta — London va New York sessiyalari ochilishidan 30 daqiqa oldin:

1. **altFINS Signals Feed**'dan so'nggi 2 soatdagi **BULLISH** signallar olinadi — faqat **kuchli turlar**:
   breakout, chart figuralari (uchburchak, bayroq, wedge, kanal, double/triple bottom, inverse H&S, harmonik),
   EMA/SMA kesishuvlari, support/resistance. Bull/Bear Power, Williams, Stochastic, RSI, MACD,
   top gainers kabi zaif/shovqinli signallar tashlanadi (`STRONG_ONLY=true`).
2. MEXC spot'da bor coinlar **kuzatuvga** olinadi.
3. Agent **2 soat davomida** har 5 daqiqada MEXC'dagi **5M shamlarni** tekshiradi.
   Har bir signal **o'z turining qoidasi** bo'yicha tasdiqlanadi (pastdagi jadval).
4. Tasdiq bo'lsa — **Entry, SL, TP1 (1:2), TP2** hisoblanadi va **faqat bitta, eng yaxshi coin**
   Telegram'ga yuboriladi. Bir vaqtda bir nechtasi tasdiqlansa — bahosi, altFINS signallari soni va
   RR bo'yicha eng kuchlisi tanlanadi. Shundan keyin o'sha sessiya kuzatuvi tugaydi.
5. Narx SL ostiga tushsa — signal bekor. 2 soatda hech biri tasdiqlanmasa — "signal yo'q" degan qisqa xabar keladi.
6. Kuzatuv davomida har 30 daqiqada altFINS'dan yangi signallar ham qo'shiladi.

| Sessiya | Kuzatuv (Toshkent vaqti) |
|---|---|
| 🇬🇧 London | 11:30–13:30 → 25-oktabrdan **12:30–14:30** |
| 🇺🇸 New York | 16:30–18:30 → 1-noyabrdan **17:30–19:30** |

Yoz/qish vaqtiga o'tishni agent o'zi hisoblaydi. Shanba-yakshanba ishlamaydi.

## 5M tasdiq qoidalari (altFINS signal turi bo'yicha)

| altFINS signali | 5M tasdiq sharti |
|---|---|
| **Breakout**: pattern breakout, resistance, uchburchak, bayroq, wedge, kanal, yangi maksimum, ATH yaqinida | 5M sham darajadan (yoki so'nggi 1 soat maksimumidan) yuqorida yopiladi, hajm o'rtachadan ≥1.5× |
| **Sham figurasi**: hammer, engulfing, morning star, piercing, tweezer bottom, three white soldiers va h.k. | 5M sham signal bergan 15M sham maksimumidan yuqorida yopiladi |
| **MACD**: signal chizig'i kesishuvi, gistogramma burilishi | 5M'da MACD > signal, gistogramma 2 sham ketma-ket o'smoqda, narx 5M EMA20 dan yuqori |
| **Osillyator**: RSI, Stochastic, Williams, oversold | 5M RSI 30 dan yuqori va o'smoqda, sham oldingi 5M maksimumdan yuqori yopiladi |
| **MA kesishuvi**: EMA 12/50, EMA 9/12, narx/EMA, SMA | 15M'da tez MA sekin MA'dan yuqori saqlanadi, 5M sham tez MA va oldingi maksimumdan yuqori yopiladi |
| **Supportdan qaytish**: horizontal support, double/triple bottom, pullback, inverse H&S, harmonik figuralar | 5M sham so'nggi 30 daqiqa maksimumidan yuqori yopiladi |
| **Trend davomi**: up trend, strong trend, momentum, OBV | 5M sham EMA20 va so'nggi 1 soat maksimumidan yuqori yopiladi |

**SL:** 15M'dagi oxirgi swing low ostida (juda yaqin/uzoq bo'lsa — 1.5×ATR).
**TP1:** 1:2. **TP2:** keyingi resistance yoki 1:3.
Resistance 1:1 dan yaqin bo'lsa yoki RSI 80 dan yuqori bo'lsa — yuborilmaydi.

**Baho** (1H trend, 15M trend, RSI, MACD, hajm) kamida **3/5** bo'lishi kerak (`MIN_SCORE`).
Ya'ni kuniga eng ko'pi bilan 2 ta signal: London va New York uchun bittadan.

## GitHub Actions'da ishlatish (kompyuter o'chiq bo'lsa ham)

1. Repozitoriy → **Settings → Secrets and variables → Actions → New repository secret**:
   - `ALTFINS_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
2. **Actions** bo'limida workflow'ni yoqing.
3. Sinov: **Actions → Signal agenti → Run workflow** (20 daqiqalik kuzatuv).

Jadval: `.github/workflows/signals.yml`.

## Kompyuterda ishlatish

```
pip install -r requirements.txt
copy config.env.example config.env     (keyin config.env ni to'ldiring)
python agent.py --get-chat-id          # botga /start yozgandan keyin
python agent.py --test-telegram
python agent.py --once --minutes 20 --dry-run --debug   # sinov
python agent.py                        # doimiy rejim
```

Boshqa buyruqlar: `--credits` (altFINS kredit qoldig'i), `--schedule` (keyingi sessiyalar).

## Fayllar

- `agent.py` — agent
- `config.env` — kalitlaringiz (**hech kimga bermang**, GitHub'ga yuklanmaydi)
- `agent.log` — ish jurnali
- `state.json` — yuborilgan coinlar (12 soat ichida takror yubormaslik)
- `altfins_raw.json` — `--debug` bilan altFINS xom javobi

> Agent faqat signal yuboradi, birjada savdo ochmaydi. Signallar moliyaviy maslahat emas.
