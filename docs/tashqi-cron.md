# Tashqi cron — postlar aniq vaqtda chiqishi uchun

## Nima uchun

GitHub Actions cron'ni belgilangan daqiqada ishga tushirishga kafolat bermaydi.
Bizning o'lchovimizda kechikish 3 soatdan **8–10 soatgacha** yetdi, ba'zi
ishlar esa umuman ishga tushmadi:

| Cron (UTC) | Rejalashtirilgan | Haqiqiy | Kechikish |
|---|---|---|---|
| `9 13` | 18:09 Toshkent | 03:59 | 9 soat 50 daqiqa |
| `9 16` | 21:09 Toshkent | 05:31 | 8 soat 22 daqiqa |
| `44 18` | 23:44 Toshkent | 06:54 | 7 soat 10 daqiqa |

Yechim: ishni GitHub navbatidan kutmasdan, **tashqaridan majburan** ishga
tushirish. `workflow_dispatch` orqali yuborilgan so'rov navbatga tushmaydi va
bir necha soniyada boshlanadi. GitHub cron'lari zaxira sifatida qoladi.

## 1. GitHub token yaratish

1. <https://github.com/settings/personal-access-tokens/new>
2. **Token name:** `FPL bot tashqi cron`
3. **Expiration:** `No expiration` (yoki 1 yil)
4. **Repository access:** `Only select repositories` → `FPLUzbekistan`
5. **Permissions → Repository permissions → Actions:** `Read and write`
6. `Generate token` → tokenni nusxalab oling (`github_pat_...`), u faqat bir
   marta ko'rsatiladi.

## 2. cron-job.org da yozuv qo'shish

<https://console.cron-job.org> → ro'yxatdan o'ting → **CREATE CRONJOB**.

Har bir yozuv uchun bir xil sozlama:

| Maydon | Qiymat |
|---|---|
| **URL** | `https://api.github.com/repos/Ilkhomjoon/FPLUzbekistan/actions/workflows/<FAYL>/dispatches` |
| **Request method** | `POST` |
| **Timezone** | `Asia/Tashkent` |
| **Headers** | `Accept: application/vnd.github+json`<br>`Authorization: Bearer <TOKEN>`<br>`X-GitHub-Api-Version: 2022-11-28`<br>`Content-Type: application/json` |
| **Request body** | quyidagi jadvalda |

> Muvaffaqiyatli so'rov **HTTP 204** qaytaradi (javob tanasi bo'sh). 401 —
> token noto'g'ri, 403 — tokenda `Actions: write` ruxsati yo'q, 404 — fayl
> nomi yoki repo nomi xato.

### Yozuvlar

| # | Fayl (`<FAYL>`) | Vaqt (Toshkent) | Request body |
|---|---|---|---|
| 1 | `price-changes.yml` | har kuni **05:45** | `{"ref":"main","inputs":{"scheduled":"true"}}` |
| 2 | `price-watch.yml` | har kuni **22:50** | `{"ref":"main","inputs":{"scheduled":"true"}}` |
| 3 | `gw-review.yml` | har kuni **12:45** | `{"ref":"main","inputs":{"scheduled":"true"}}` |
| 4 | `differentials.yml` | har kuni **19:50** | `{"ref":"main","inputs":{"scheduled":"true"}}` |
| 5 | `live-bonus.yml` | **:10** — 13,14,…,23 va 00,01,02 soatlarda | `{"ref":"main","inputs":{"scheduled":"true"}}` |
| 6 | `live-bonus.yml` | **:10** — 06, 08, 10 soatlarda | `{"ref":"main","inputs":{"scheduled":"true","final":"true"}}` |
| 7 | `deadline-stats.yml` | **:20** — 12, 15, 18, 21, 00 soatlarda | `{"ref":"main","inputs":{"scheduled":"true"}}` |

5–7-yozuvlarda cron-job.org jadval oynasida kerakli **soatlarni belgilab**,
daqiqa sifatida bittasini (`10` yoki `20`) tanlang.

### Nega bu vaqtlar

Har bir post o'z vaqtidan biroz oldin chaqiriladi va **kerakli daqiqani
jarayonning o'zi kutadi**:

- `price-changes` 05:45 da uyg'onadi → 06:00 da post
- `price-watch` 22:50 da uyg'onadi → 23:00 da post
- `differentials` 19:50 da uyg'onadi → 20:00 da post
- `gw-review` 12:45 da uyg'onadi → FPL lockdown'ini kuzatadi (~13:05)
- `live-bonus` har soat tekshiradi; o'yin yo'q bo'lsa 20 soniyada chiqadi
- `deadline-stats` deadline yaqinlashganini o'zi hisoblaydi

## 3. Tekshirish

Bitta yozuvni qo'lda ishga tushiring (cron-job.org da **TEST RUN**), so'ng
GitHub → Actions bo'limida yangi run paydo bo'lganini ko'ring. Run
nomida `Manually run by` emas, `workflow_dispatch` yozuvi turadi.

Loglarda:

```
Post vaqtini kutyapmiz: 23:00:00 gacha 9 daqiqa qoldi.
```

## Xavfsizlik

- Token faqat bitta repozitoriyga va faqat `Actions` ga ruxsat beradi —
  kod o'qish/yozish, secret'lar yoki boshqa repolarga tegmaydi.
- Token cron-job.org da saqlanadi. Shubha tug'ilsa GitHub'dan bir bosishda
  bekor qilib, yangisini yaratasiz.
- Telegram tokeni va kanal id'si GitHub Secrets'da qoladi — cron-job.org
  ularni ko'rmaydi.

## GitHub cron'lari nima bo'ladi

Ular joyida qoladi va **zaxira** bo'lib ishlaydi: tashqi cron biror sababga
ko'ra ishlamasa, GitHub kech bo'lsa ham ishga tushiradi. Ikki marta post
chiqmasligini holat fayllari va `--window` chegaralari ta'minlaydi.
