# FPLUzbekistan boti

[@FPLUzbekistan](https://t.me/FPLUzbekistan) kanali uchun ikkita avtomatlashtirilgan vazifa:

1. **Narx o'zgarishlari** — har kuni ertalab futbolchilarning narxi tushgan/ko'tarilganini aniqlab, tayyor shablon bo'yicha post qiladi. O'zgarish bo'lmasa **hech narsa post qilinmaydi**, faqat logga yoziladi.
2. **Jonli bonus ochkolar** — o'yin kuni birinchi o'yin boshlanishi bilan kanalga bitta xabar yuboradi va uni **har daqiqada** yangilab boradi (BPS asosidagi bonus, hisob, 🔴 → 🟢).

Hammasi **GitHub Actions**da, mutlaqo tekin ishlaydi. Server sotib olish shart emas.

---

## 1. Tez boshlash

### 1.1. Telegram bot yaratish

1. Telegramda [@BotFather](https://t.me/BotFather) ga yozing → `/newbot`
2. Nom va username bering → sizga **token** beradi (`123456789:AA...`)
3. Botni **@FPLUzbekistan** kanaliga **administrator** qilib qo'shing (kamida "Post messages" va "Edit messages of others" huquqlari bilan — xabarni tahrirlash uchun ikkinchisi shart emas, lekin o'z xabarini tahrirlash uchun bot admin bo'lishi kerak).
4. Xatolik ogohlantirishlari uchun: botga shaxsiy chatda `/start` yozing, so'ng [@userinfobot](https://t.me/userinfobot) dan o'z `chat_id` ingizni oling.

### 1.2. Repozitoriy

Avval **github.com** da yangi bo'sh repo yarating (README, .gitignore, litsenziya **qo'shmang**), keyin papkangizda:

```bash
git init
git add .
git commit -m "FPLUzbekistan bot"
git branch -M main
git remote add origin https://github.com/FOYDALANUVCHI/fpl-uzbekistan-bot.git
git push -u origin main
```

`gh` CLI o'rnatilgan bo'lsa, hammasi bitta buyruq bilan:

```bash
git init && git add . && git commit -m "FPLUzbekistan bot"
gh repo create fpl-uzbekistan-bot --public --source=. --push
```

> ⚠️ **Repozitoriy public bo'lsin.** GitHub Actions public repolarda cheksiz tekin, private repolarda esa oyiga faqat 2000 daqiqa — jonli bonus jarayoni buni tez tugatib qo'yadi. Token va boshqa maxfiy ma'lumotlar kodda emas, **Secrets** ichida saqlanadi, shuning uchun public repo xavfsiz.

**Push qilishdan oldin tekshiring:** `.env` fayl `.gitignore` da bor, ya'ni GitHub'ga tushmaydi. Ishonch hosil qilish uchun:

```bash
git status --short          # ro'yxatda .env ko'rinmasligi kerak
```

Agar tasodifan token bilan commit qilib yuborgan bo'lsangiz — repo'dan o'chirish yetarli emas, **BotFather → /revoke** orqali tokenni bekor qilib, yangisini oling.

### 1.3. Secrets qo'shish

Repo → **Settings → Secrets and variables → Actions → New repository secret**:

| Nom | Qiymat |
|---|---|
| `TELEGRAM_BOT_TOKEN` | BotFather bergan token |
| `TELEGRAM_CHANNEL_ID` | `@FPLUzbekistan` |
| `TELEGRAM_ADMIN_CHAT_ID` | sizning shaxsiy chat id (ixtiyoriy) |

### 1.4. Telegramda mock test

Kanalga tegmasdan, avval **o'zingizga** soxta ma'lumot yuborib ko'ring:

```bash
python -m tests.mock_demo --send
```

Agar xatolik chiqsa, avval diagnostikani ishga tushiring — u `.env` topilganmi, token to'g'rimi, bot kanalda administratormi, hammasini bir joyda ko'rsatadi:

```bash
python -m scripts.doctor
```

Bu `.env` dagi `TELEGRAM_ADMIN_CHAT_ID` ga yuboradi va quyidagilarni ketma-ket sinaydi:

1. Token to'g'riligi (`getMe`)
2. Narx tushishi posti
3. Narx ko'tarilishi posti
4. Jonli bonus xabari — yuboriladi, so'ng **8 soniyada bir marta 2 marta tahrirlanadi** (o'yin davom etyapti → gol → hammasi tugadi)

Eng muhimi 4-qadam: xabar **yangi post sifatida emas, o'sha xabarning o'zi o'zgarib** turishi kerak. Emoji 🔴 dan 🟢 ga aylanadi va "So'ngi yangilanish" vaqti yangilanadi.

Hammasi joyida bo'lsa, kanalga yuboring:

```bash
python -m tests.mock_demo --send --to @FPLUzbekistan
```

Kanalga yuborganda bot administrator ekanini va "Post messages" huquqi borligini ham tekshiradi. Test xabarlarini keyin qo'lda o'chirib tashlaysiz.

```bash
python -m tests.mock_demo --send --to @FPLUzbekistan --pause 20   # sekinroq kuzatish uchun
```

### 1.5. Birinchi haqiqiy ishga tushirish

Repo → **Actions → "Narx o'zgarishlari" → Run workflow**.

Birinchi ishga tushirishda bot faqat **boshlang'ich snapshot**ni oladi va hech narsa post qilmaydi — bu normal holat. Ertasi kunidan boshlab solishtira boshlaydi.

---

## 2. Lokal sinash (dry-run)

> **Dry-run uchun token kerak emas.** `--dry-run` rejimida bot Telegramga umuman ulanmaydi — matnni ekranga chiqaradi, xolos. `.env` faylsiz ham ishlaydi.

### Windows (PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

python -m tests.mock_demo                        # internetsiz, soxta ma'lumot bilan namuna
python -m bot.price_changes --preview            # HAQIQIY ma'lumot bilan namuna
python -m bot.live_bonus --dry-run --once        # jonli xabarni bir marta chizib berish
python -m unittest discover -s tests             # bonus qoidalari testlari
```

Agar `Activate.ps1` ni PowerShell bloklasa, bir marta shu buyruqni bering:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

`cmd.exe` ishlatsangiz faollashtirish `.venv\Scripts\activate.bat` bo'ladi.

### macOS / Linux

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m tests.mock_demo
python -m bot.price_changes --preview
python -m bot.live_bonus --dry-run --once
python -m unittest discover -s tests
```

### Qaysi buyruq nima qiladi

| Buyruq | Internet | Nima ko'rsatadi |
|---|---|---|
| `python -m tests.mock_demo` | kerak emas | Soxta ma'lumot bilan ikkala post turi ham |
| `python -m bot.price_changes --preview` | kerak | Haqiqiy futbolchilar va narxlar bilan namuna |
| `python -m bot.live_bonus --dry-run --once` | kerak | Bugungi o'yinlar bo'yicha jonli xabar (o'yin bo'lmasa "o'yin yo'q" deydi) |
| `python -m bot.price_changes --dry-run` | kerak | Haqiqiy ish jarayoni: snapshot bilan solishtiradi |

**Muhim nuance:** `--dry-run` ni birinchi marta ishga tushirganingizda hech qanday post chiqmaydi — bu xato emas. Solishtirish uchun kechagi narxlar kerak, birinchi ishga tushishda bot faqat boshlang'ich snapshot oladi. Shuning uchun **birinchi sinov uchun `--preview` ni ishlating** — u snapshot'ga bog'liq emas va postni darhol chizib beradi.

### Token bilan sinash (ixtiyoriy)

Haqiqiy yuborishni sinamoqchi bo'lsangiz `.env` fayl yarating:

```powershell
copy .env.example .env
notepad .env
```

Ichida **qo'shtirnoq kerak emas**, bo'sh joy ham qo'ymang:

```ini
TELEGRAM_BOT_TOKEN=8123456789:AAH_bLaBlaBlaTokeningiz
TELEGRAM_CHANNEL_ID=@FPLUzbekistan
```

Xato variantlar: `TELEGRAM_BOT_TOKEN="812..."` (qo'shtirnoq token ichiga kirib ketadi), `TELEGRAM_BOT_TOKEN = 812...` (bo'sh joy).

> Notepad'da saqlaganda "Save as type" ni **All Files** qilib, nomini aniq `.env` deb yozing — aks holda Windows `.env.txt` qilib saqlab qo'yadi va bot uni ko'rmaydi. Fayl kengaytmalarini ko'rish uchun: Explorer → View → File name extensions.

---

## 3. Vaqt jadvali — "erta uyg'on, ichida kut"

### Muammo

GitHub Actions cron'ni **belgilangan daqiqada boshlashga kafolat bermaydi**. Bizning o'lchovlarimiz (78 ta ishga tushish):

| Workflow | O'rtacha kechikish | Median | Eng yomon |
|---|---|---|---|
| Jonli bonus | 17 daqiqa | 10 daqiqa | 102 daqiqa |
| Narx o'zgarishlari | **66 daqiqa** | 65 daqiqa | 76 daqiqa |

Ya'ni "aniq 06:00 da uyg'on" degan cron postni 07:06 da chiqarardi.

### Yechim

Cron'ning **aniqligiga** emas, **zaxirasiga** tayanamiz. Ish bir marta boshlangach, uning ichidagi vaqt aniq — `sleep` soniyagacha to'g'ri ishlaydi. Shuning uchun:

```
❌  aniq 06:00 da uyg'on        →  GitHub 07:06 da uyg'otadi  →  post kechikadi
✅  04:07 da uyg'on, ichida kut  →  GitHub 05:13 da uyg'otsa ham,
                                   jarayon 06:00:00 gacha kutib turadi
```

Har bir workflow shu tamoyilda ishlaydi:

| Post | Cron uyg'onadi | Jarayon ichida | Post chiqadi |
|---|---|---|---|
| Narx o'zgarishlari | 04:07 | narx o'zgarishini kuzatadi, so'ng `PRICE_POST_AT` gacha ushlab turadi | **06:00** |
| Jonli bonus | o'yindan ≤115 daqiqa oldin | birinchi o'yin boshlanishini uxlab kutadi | **o'yin boshlanishida** |
| Deadline statistikasi | o'yindan ≤200 daqiqa oldin | `T−40 daqiqa` gacha kutadi, so'ng ligalarni skanerlaydi | **T−40 daqiqa** |
| Narx bashorati | 22:09 | `--post-at 23:00` | **23:00** |
| Differentiallar | 19:09 | `DIFF_POST_AT` gacha ushlab turadi | **20:00** |
| Tur sharhi | 12:30 | FPL tasdig'ini kuzatadi | **~13:05** (qishda ~14:05) |

**Tur sharhi — alohida holat.** 2026/27 dan FPL ochkolarni turning oxirgi o'yinidan keyingi kuni **Britaniya vaqti bilan 09:00** da yakuniy qiladi ("lockdown"). Toshkentda bu yozda 13:00, qishda 14:00 — ya'ni aniq soatni cron'ga yozib bo'lmaydi. Shuning uchun 12:30 da uyg'onib, har 3 daqiqada tekshiramiz va tayyor bo'lishi bilan chiqaramiz (`GW_REVIEW_UNTIL` gacha).

**Muhim:** `bootstrap-static` dagi `finished` bayrog'i lockdown'dan ancha keyin qo'yiladi — unga tayanib bo'lmaydi. Turning yakunlanganini `/event-status/` bo'yicha aniqlaymiz:

| Maydon | Yakunlanmagan | Yakunlangan |
|---|---|---|
| `points` | `"p"` (provisional) | `"r"` (results) |
| `bonus_added` | `false` | `true` |
| `leagues` | `"Updating"` | `""` |

Uchalasi ham tayyor bo'lgandagina post chiqadi. `leagues: "Updating"` ni ham kutamiz, chunki sharh liga jadvallarini o'qiydi — aks holda o'rinlar yarim hisoblangan holatda chiqib qolardi.

`data_checked` jarayonning eng oxirgi qadami va bir necha soat kechikadi — unga tayanmaymiz.

**CDN haqida.** FPL API'ni ketma-ket so'raganda turli serverlar turli yoshdagi nusxani qaytaradi — bitta so'rov "tayyor", keyingisi "tayyor emas" deyishi mumkin. Shuning uchun post chiqishidan oldin `GW_REVIEW_CONFIRM` (2) marta ketma-ket tasdiq talab qilinadi, orasida 30 soniya tanaffus bilan.

Har birida **zaxira cron** ham bor — GitHub ba'zan rejalashtirilgan run'ni umuman tashlab ketadi. Holat fayllari tufayli ikki marta post chiqmaydi.

### Yon foyda: uyg'onishlar soni 5 barobar kamaydi

| | Ilgari | Hozir |
|---|---|---|
| Jonli bonus | 56 ta/kun | 13 ta/kun |
| Deadline statistikasi | 56 ta/kun | 5 ta/kun |
| Qolganlari | 6 ta/kun | 10 ta/kun |
| **Jami** | **~118 ta/kun** | **~28 ta/kun** |

Bu o'z-o'zidan kechikishni kamaytiradi: GitHub bitta repodan kelayotgan so'rovlarni ham hisobga oladi. Ochiq (public) repoda daqiqalar cheksiz va tekin, shuning uchun "uxlab turgan" ish hech narsaga tushmaydi.

Cron daqiqalari ham ataylab **g'alati** tanlangan (`:07`, `:11`, `:13`, `:23`, `:41`, `:44`): `:00`, `:15`, `:30`, `:45` — butun dunyo bo'yicha eng band daqiqalar, aynan o'sha paytda kechikish eng katta bo'ladi.

### Jonli bonus: 115 daqiqa va 1 daqiqa — bu ikki xil narsa

| Nima | Qanchada bir | Nima uchun |
|---|---|---|
| **Cron uyg'onishi** | har **90 daqiqada**, 08:11–21:41 UTC | "Bugun o'yin bormi?" deb qarash uchun |
| **`LIVE_START_LEAD`** | **115 daqiqa** | O'yingacha shundan kam qolgan bo'lsa jarayon chiqmaydi, kutadi |
| **Xabar yangilanishi** | har **1 daqiqada** | Kanaldagi post shu tezlikda tahrirlanadi |

115 > 90 bo'lgani muhim: uyg'onishlar orasidagi masofadan kattaroq, shuning uchun **har bir o'yin albatta qamrab olinadi**.

Yangilanish tezligini `LIVE_INTERVAL` (soniyada) bilan o'zgartirasiz. 60 soniyadan pastga tushirishni tavsiya qilmayman: FPL API'ni ortiqcha yuklaydi va Telegram tahrirlash limitiga yaqinlashadi.

### Kechikishni o'lchash

Har ishga tushishda bot `data/cron_log.csv` ga yozib boradi. Hisobot:

```bash
git pull                              # Actions yozgan loglarni oling
python -m scripts.cron_delay --report
```

Ikkita ustun bor va ular boshqa-boshqa narsa:

- **`delay_seconds`** — GitHub cron'ning haqiqiy kechikishi (run yaratilgan vaqt vs rejalashtirilgan vaqt).
- **`queued_seconds`** — run yaratilgandan keyin job navbatda turgan vaqt. Bu cron aybi emas: masalan jonli bonus jarayoni 5 soat ishlab, `concurrency` guruhini band qilib turadi va keyingi uyg'onish navbatda kutadi.

Ogohlantirish chegarasi endi **90 daqiqa** (`CRON_ALERT_MINUTES`) — kechikish post vaqtiga ta'sir qilmagani uchun har 20 daqiqalik kechikishda xabar kelishi shart emas.

> Qo'lda ishga tushirilgan (`Run workflow`) holatlar hisobga olinmaydi — faqat cron bo'yicha ishga tushishlar yoziladi.

### FPL narx o'zgarishi vaqti

FPL narxlarni **Britaniya vaqti bilan 01:30** da o'zgartiradi:

| Mavsum | Britaniya vaqti | UTC | Toshkent |
|---|---|---|---|
| Yozgi (BST) | 01:30 | 00:30 | 05:30 |
| Qishgi (GMT) | 01:30 | 01:30 | 06:30 |

Kuzatuv rejimi ikkalasini ham o'zi hal qiladi: o'zgarishni ko'rmaguncha `PRICE_WATCH_UNTIL` (07:30) gacha kutadi. Yozda o'zgarish 05:30 da topiladi va post 06:00 da chiqadi; qishda o'zgarish 06:30 da topiladi va post o'sha zahoti chiqadi.

---

## 4. Fayllar

```
bot/
  config.py         # sozlamalar (.env / GitHub Secrets)
  fpl_api.py        # FPL API bilan ishlash
  telegram.py       # sendMessage / editMessageText, xatolik ogohlantirishi
  storage.py        # JSON holat fayllari (atomik yozish)
  bonus.py          # BPS -> bonus ochko (teng holatlar qoidasi bilan)
  defcon.py         # Defensive Contribution ochkolari
  formatting.py     # post matnlarini yig'ish
  waiter.py         # "erta uyg'on, ichida kut" — cron kechikishiga qarshi
  price_changes.py  # 1-vazifa: kunlik narx o'zgarishlari
  live_bonus.py     # 2-vazifa: jonli bonus ochkolar
  differentials.py  # tur oralig'idagi differentiallar posti + so'rovnoma
data/
  prices.json       # kechagi narxlar snapshot'i (Actions o'zi commit qiladi)
  live_message.json # bugungi jonli xabar id'si
  cron_log.csv      # cron kechikish tarixi
  differentials.json # qaysi tur uchun differentiallar chiqarilgani
.github/workflows/  # ikkita cron
scripts/
  commit_state.sh   # holat fayllarini repoga commit qiladi
  cron_delay.py     # cron kechikishini o'lchaydi va hisobot beradi
tests/
```

Holat fayllari (`data/`) workflow tomonidan avtomatik repoga commit qilinadi — shu sababli baza yoki tashqi xotira kerak emas. Bu bir yo'la yana bir foyda beradi: GitHub 60 kun harakatsiz repolarda cron'ni o'chirib qo'yadi, kunlik commit buni oldini oladi.

---

## 5. Sozlash

Barcha sozlamalar `.env` yoki GitHub Secrets/Variables orqali:

| O'zgaruvchi | Standart | Nima qiladi |
|---|---|---|
| `DRY_RUN` | `false` | `true` — Telegramga yubormaydi |
| `CHANNEL_TAG` | `@FPLUzbekistan` | Post oxiridagi taq |
| `PRICE_HASHTAG` | `#PriceChanges` | Narx posti hashtagi |
| `PRICE_SHOW_TEAM` | `false` | `true` — `Cherki (MCI) (£6.5M)` ko'rinishi |
| `PRICE_POST_AT` | `06:00` | `--watch` rejimida post aynan shu vaqtda chiqadi |
| `PRICE_WATCH_UNTIL` | `07:30` | Shu vaqtgacha o'zgarish bo'lmasa — post yo'q |
| `PRICE_POLL` | `120` | `--watch` necha soniyada bir tekshiradi |
| `LIVE_HASHTAG` | `#BonusPoints` | Jonli post hashtagi |
| `SHOW_BPS` | `true` | Bonus yonida BPS ko'rsatilsinmi (`3 · 34 BPS`) |
| `SHOW_DEFCON` | `true` | 🛡 DefCon qatori chiqsinmi |
| `DEFCON_TTL` | `120` | DefCon necha soniyada bir yangilanadi |
| `LIVE_INTERVAL` | `60` | Necha soniyada bir yangilanadi |
| `LIVE_MAX_MINUTES` | `300` | Bitta jarayon maksimal ish vaqti |
| `LIVE_FINISH_GRACE` | `10` | Oxirgi o'yin tugagach yana necha daqiqa kuzatadi (rasmiy bonus uchun) |
| `LIVE_START_LEAD` | `5` (workflow'da `115`) | O'yingacha shundan kam qolsa jarayon chiqmaydi, kutadi |
| `LIVE_PREKICK_POLL` | `60` | O'yingacha shuncha soniya qolganda uyqudan turadi |
| `STATS_WAKE_LEAD` | `300` (workflow'da `200`) | `--wait` rejimida shundan kam qolsa kutib turadi |
| `ERROR_ALERT_AFTER` | `3` | Necha marta ketma-ket xatodan keyin ogohlantirsin |
| `CRON_ALERT_MINUTES` | `20` (workflow'da `90`) | Cron kechikishi haqida ogohlantirish chegarasi |
| `GW_REVIEW_UNTIL` | `18:00` | FPL tasdig'ini shu vaqtgacha kutadi |
| `GW_REVIEW_POLL` | `180` | Tasdiqlanganini necha soniyada bir tekshiradi |
| `GW_REVIEW_CONFIRM` | `2` | Necha marta ketma-ket tasdiq talab qilinadi (CDN uchun) |
| `DIFF_POST_AT` | `20:00` | Differentiallar posti qachon chiqadi |
| `DIFF_LATEST` | `23:00` | Bundan kech bo'lsa post ertangi kunga suriladi |
| `DIFF_MAX_OWN` | `10` | "Differential" hisoblanish chegarasi, egalik % |
| `DIFF_MIN_POINTS` | `7` | O'tgan turda shundan kam olgani ro'yxatga tushmaydi |
| `DIFF_TOP100_SIZE` | `100` | Dunyo bo'yicha nechta menejer tarkibi skanerlanadi |
| `DIFF_TOP100_MIN` | `12` | Top-100 da shundan ko'p bo'lsa qiziq deb hisoblanadi |
| `DIFF_LOCAL_LEAGUE` | `true` | "Bizning ligada" bo'limi chiqsinmi |
| `DIFF_POLL` | `true` | Postdan keyin so'rovnoma yuborilsinmi |
| `LOCAL_TZ` | `Asia/Tashkent` | Xabardagi vaqtlar shu zonada ko'rsatiladi |
| `MATCHDAY_TZ` | `Europe/London` | "O'yin kuni" shu zona bo'yicha aniqlanadi |

`MATCHDAY_TZ` nega London? Shanba kuni 19:30 (London) da boshlanadigan o'yin Toshkentda allaqachon **yakshanba 00:30** bo'ladi. London bo'yicha guruhlansa, o'sha kunning barcha o'yinlari bitta xabarda qoladi.

---

## 6. Bonus ochkolar qanday hisoblanadi

O'yin davomida FPL rasmiy bonusni bermaydi — faqat **BPS** (Bonus Points System) ko'rsatkichini beradi. Bot shu BPS'dan taxminiy bonusni hisoblaydi:

- eng yuqori BPS → 3, ikkinchi → 2, uchinchi → 1
- 1-o'rinda 2 kishi teng → ikkalasi 3, keyingisi 1 (2 berilmaydi)
- 1-o'rinda 3+ kishi teng → hammasi 3, boshqa hech kim olmaydi
- 2-o'rinda teng → hammasi 2, 1 berilmaydi
- 3-o'rinda teng → hammasi 1

O'yin tugagach FPL rasmiy `bonus` qiymatini beradi — o'shanda bot taxminiy hisobni tashlab, rasmiy raqamga o'tadi.

### DefCon (Defensive Contribution)

Har bir o'yin ostida DefCon ochkosini olgan futbolchilar alohida qatorda chiqadi:

```
🔴 Man City 2:1 Man Utd
Haaland (MCI) — 3 · 38 BPS
Khusanov (MCI) — 2 · 30 BPS
Casemiro (MUN) — 1 · 22 BPS
🛡 DefCon: Casemiro (MUN), Gvardiol (MCI), Khusanov (MCI)
```

Qoida (2025/26 da joriy etilgan, 2026/27 da o'zgarmagan):

| Pozitsiya | Chegara | Nima hisoblanadi |
|---|---|---|
| Himoyachi (DEF) | **10** | Clearances + blocks + interceptions + tackles (CBIT) |
| Yarim himoyachi / hujumchi (MID, FWD) | **12** | CBIT + ball recoveries (CBIRT) |
| Darvozabon (GK) | — | Bu ochkoni ololmaydi |

Bir o'yinda maksimum **2 ochko** — 20 ta harakat qilsa ham 2 ta beriladi.

Ma'lumot `/api/event/{gw}/live/` dan olinadi. Asosiy manba — FPL'ning o'z `defensive_contribution` identifikatori (o'yin bo'yicha aniq). Agar API uni bermasa, bot yuqoridagi qoida bo'yicha o'zi hisoblaydi — lekin faqat futbolchining o'sha turda bitta o'yini bo'lsa, chunki `stats` bloki tur bo'yicha yig'indi beradi va double gameweek'da ikki o'yin aralashib ketadi.

DefCon ma'lumoti `DEFCON_TTL` (standart 120 soniya) bo'yicha yangilanadi — bonusdan sekinroq, chunki bu so'rov ancha og'ir. Kerak bo'lmasa `SHOW_DEFCON=false` bilan o'chirasiz.

---

## 7. Boshqa hosting variantlari

GitHub Actions eng arzon (tekin) va eng oddiy yo'l, lekin cron kechikishi va 6 soatlik job limiti bor. Agar keyinchalik barqarorroq variant kerak bo'lsa:

| Variant | Narx | Izoh |
|---|---|---|
| **GitHub Actions** (hozirgi) | Tekin (public repo) | Sozlash oson, holat repoda. Cron 5–20 daqiqa kechikishi mumkin |
| **Oracle Cloud Free Tier** | Tekin (doimiy) | 4 CPU / 24 GB ARM VM. Karta biriktirish kerak, ro'yxatdan o'tish qiyinroq |
| **Hetzner / Contabo VPS** | ~4–5 $/oy | Eng barqaror. `systemd` timer + doimiy `live_bonus` xizmati |
| **Railway / Fly.io** | Tekin limit yoki ~5 $/oy | Docker bilan deploy oson |

VPS'ga o'tsangiz kod o'zgarmaydi — faqat cron o'rniga `systemd` ishlatiladi:

```ini
# /etc/systemd/system/fpl-price.timer
[Timer]
OnCalendar=*-*-* 06:00:00 Asia/Tashkent
```

va `live_bonus` ni `Restart=always` bilan doimiy xizmat qilib qo'yiladi (skript o'yin yo'q kunlari darhol chiqadi, shuning uchun tashqi cron ham kerak).

---

## 8. Tez-tez uchraydigan muammolar

| Muammo | Yechim |
|---|---|
| `Forbidden: bot is not a member of the channel chat` | Botni kanalga admin qilib qo'shing |
| Xabar tahrirlanmayapti | Bot admin bo'lishi va "Post messages" huquqi bo'lishi kerak |
| Cron ishlamayapti | Repo 60 kun harakatsiz bo'lsa GitHub cron'ni o'chiradi — Actions sahifasida qayta yoqing |
| Post ikki marta chiqdi | `data/live_message.json` commit bo'lmay qolgan — Actions loglarini tekshiring |
| Birinchi kuni post yo'q | Normal: birinchi ishga tushish faqat snapshot oladi. Darhol ko'rish uchun `--preview` |
| Windows: `UnicodeEncodeError` | Kodda tuzatilgan. Baribir chiqsa: `set PYTHONUTF8=1` yoki `chcp 65001` |
| Windows: emoji o'rniga kvadratchalar | Eski `cmd.exe` kamchiligi — Windows Terminal yoki PowerShell ishlating. Telegramda emoji baribir to'g'ri chiqadi |
| Windows: `.env` o'qilmayapti | `python -m scripts.doctor` ishga tushiring — sababini aytadi. Ko'pincha fayl `.env.txt` bo'lib saqlangan |
| `XATO: qabul qiluvchi topilmadi` | `.env` o'qilmagan. `python -m scripts.doctor` bilan tekshiring |
| `Sozlama yetishmayapti: TELEGRAM_BOT_TOKEN` | `--dry-run` yoki `--preview` bilan ishlating — ularga token kerak emas |
