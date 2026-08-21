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

## 3. Vaqt jadvali haqida muhim eslatma

FPL narxlarni **Britaniya vaqti bilan 01:30** da o'zgartiradi:

| Mavsum | Britaniya vaqti | UTC | Toshkent |
|---|---|---|---|
| Yozgi (BST, mart oxiri – oktabr oxiri) | 01:30 | **00:30** | 05:30 |
| Qishgi (GMT, oktabr oxiri – mart oxiri) | 01:30 | **01:30** | 06:30 |

Shuning uchun workflow'da **ikkita cron** bor:

- `0 1 * * *` → **06:00 Toshkent** (yozgi vaqtda narxlar allaqachon o'zgargan)
- `45 1 * * *` → **06:45 Toshkent** (qishgi vaqt uchun zaxira)

Ikki marta ishlashi xavfsiz: bot snapshot bilan solishtirgani uchun, birinchi ishga tushishda o'zgarish topilmasa hech narsa post qilmaydi, ikkinchisi esa o'zgarishlarni tutadi. Ya'ni **kuniga aniq bitta post** chiqadi.

> GitHub Actions cron'i kafolatlangan aniqlikda emas — yuklama ko'p bo'lganda 5–20 daqiqa kechikishi mumkin. Agar aniq 06:00 juda muhim bo'lsa, 3-bo'limdagi VPS variantiga qarang.

### Jonli bonus: 30 daqiqa va 1 daqiqa — bu ikki xil narsa

Bu yerda ikkita alohida vaqt bor, ularni aralashtirmaslik kerak:

| Nima | Qanchada bir | Nima uchun |
|---|---|---|
| **Cron uyg'onishi** (tekshiruv) | har **30 daqiqada**, 11:00–22:59 UTC | Faqat "bugun o'yin bormi, boshlandimi?" deb qarash uchun |
| **Bonus ochkolar yangilanishi** (post) | har **1 daqiqada** | Kanaldagi xabar shu tezlikda tahrirlanadi |

Ya'ni **bonus ochkolar kanalda har daqiqada yangilanadi** — 30 daqiqa bu bilan bog'liq emas.

Nega shunday? GitHub Actions doimiy ishlab turadigan server emas — uni vaqti-vaqti bilan "uyg'otish" kerak. Shuning uchun:

1. Har 30 daqiqada cron skriptni ishga tushiradi.
2. Skript qaraydi: bugun o'yin bormi va boshlanganmi?
   - **Yo'q** bo'lsa → bir necha soniyada chiqib ketadi, hech narsa post qilinmaydi.
   - **Ha** bo'lsa → jarayon **ochiq qoladi** va 5+ soat davomida ichida `while` sikli aylanadi: har **60 soniyada** FPL API'dan BPS'ni olib, kanaldagi xabarni tahrirlaydi.

Demak eng yomon holatda o'yin boshlanishi bilan post chiqishi orasida 30 daqiqagacha kechikish bo'lishi mumkin (cron hali uyg'onmagan bo'lsa). Buni kamaytirish uchun `live-bonus.yml` dagi cron'ni tez-tezroq qilsangiz bo'ladi:

```yaml
- cron: "0,15,30,45 11-22 * * *"   # har 15 daqiqada tekshiradi
```

Yangilanish tezligini o'zgartirish uchun esa `LIVE_INTERVAL` (soniyada) sozlamasini ishlating — masalan `30` qilsangiz, xabar yarim daqiqada bir yangilanadi. 60 soniyadan pastga tushirishni tavsiya qilmayman: FPL API'ni ortiqcha yuklaydi va Telegram tahrirlash limitiga yaqinlashadi.

### Kechikishni o'lchash (GitHub Actions yetarlimi?)

Har ishga tushishda bot "rejalashtirilgan vaqt" va "haqiqiy vaqt" farqini `data/cron_log.csv` ga yozib boradi. Hech narsa qilish shart emas — workflow'lar ichida avtomatik ishlaydi.

Bir necha tur o'tgach hisobotni ko'ring:

```bash
git pull                              # Actions yozgan loglarni oling
python -m scripts.cron_delay --report
```

```
Jami yozuv: 28 ta (2026-08-10 — 2026-08-23)

Workflow                      Soni      O'rtacha        Median     Eng yomon
----------------------------------------------------------------------------
Jonli bonus                     14  1 daq 10 son       47 soniya  4 daq 05 son
Narx o'zgarishlari              14  2 daq 14 son  1 daq 30 son  6 daq 50 son

90% hollarda kechikish: 4 daq 05 son dan kam
10 daqiqadan ortiq kechikkan: 0 marta (0%)

Xulosa: GitHub Actions yetarli — kechikish sezilarli emas.
```

Xulosa uch xil bo'ladi:

| Eng yomon kechikish | Tavsiya |
|---|---|
| 5 daqiqagacha | GitHub Actions yetarli, hech narsa o'zgartirmang |
| 5–15 daqiqa | Narx posti uchun muammo emas; jonli bonus tez boshlanishi muhim bo'lsa cron'ni 15 daqiqaga tushiring |
| 15 daqiqadan ko'p, tez-tez | VPS'ga o'tish vaqti keldi (7-bo'limga qarang) |

Bundan tashqari, agar biror ishga tushish **20 daqiqadan ortiq** kechiksa, sizga darhol Telegram orqali ogohlantirish keladi (`TELEGRAM_ADMIN_CHAT_ID` o'rnatilgan bo'lsa). Chegarani `CRON_ALERT_MINUTES` bilan o'zgartirasiz.

> Qo'lda ishga tushirilgan (`Run workflow`) holatlar hisobga olinmaydi — faqat cron bo'yicha ishga tushishlar yoziladi.

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
  price_changes.py  # 1-vazifa: kunlik narx o'zgarishlari
  live_bonus.py     # 2-vazifa: jonli bonus ochkolar
data/
  prices.json       # kechagi narxlar snapshot'i (Actions o'zi commit qiladi)
  live_message.json # bugungi jonli xabar id'si
  cron_log.csv      # cron kechikish tarixi
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
| `LIVE_HASHTAG` | `#BonusPoints` | Jonli post hashtagi |
| `SHOW_BPS` | `true` | Bonus yonida BPS ko'rsatilsinmi (`3 · 34 BPS`) |
| `SHOW_DEFCON` | `true` | 🛡 DefCon qatori chiqsinmi |
| `DEFCON_TTL` | `120` | DefCon necha soniyada bir yangilanadi |
| `LIVE_INTERVAL` | `60` | Necha soniyada bir yangilanadi |
| `LIVE_MAX_MINUTES` | `300` | Bitta jarayon maksimal ish vaqti |
| `LIVE_FINISH_GRACE` | `10` | Oxirgi o'yin tugagach yana necha daqiqa kuzatadi (rasmiy bonus uchun) |
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
