# Telegram savdo boti — «Yangi o'zbek kirill alifbosiga o'tkazuvchi dastur»

TZ (`TZ_tg_sale_bot.md`) asosida yozilgan to'lov va savdo boti.
**Русская версия — в конце файла.**

## Imkoniyatlar

**Foydalanuvchi uchun**
- `/start` — ID, ism, familiya, username avtomatik saqlanadi (`/start ref_insta` — reklama manbasi ham yoziladi)
- Mahsulot haqida ma'lumot + **🛒 Sotib olish** → karta raqami, egasi, summa
- Chek (rasm yoki JPG/PNG/PDF fayl) → *«Qabul qilindi, 1 soat ichida havola yuboriladi»*
- Tasdiqlangach havola avtomatik keladi; rad etilsa — sabab va **🔄 Qayta yuborish**
- **Toza chat**: chatda bitta bot xabari turadi — tahrirlanadi yoki o'chirib-yangilanadi; noto'g'ri xabarlar o'chadi

**Admin uchun** (`/admin`)
- Har bir chek **barcha adminlarga** keladi: **✅ Tasdiqlash / ❌ Rad etish** (tayyor sabablar yoki o'z sababingiz)
- 2 admin bir vaqtda bossa ham havola **faqat 1 marta** yuboriladi; qaror barcha adminlarda ko'rinadi
- Takroriy (avval ishlatilgan) chek ⚠️ belgilanadi; «Soxta chek» → userni bir bosishda bloklash
- 50 daqiqada ko'rilmagan to'lovlar haqida eslatma
- Pastki menyu: **⚙️ Sozlamalar** (karta, egasi, narx, matn, rasm, havola turi, kanal, sotuvni yoqish/o'chirish, adminlar) ·
  **👥 Userlar** (statistika, qidirish, ro'yxat, kartochka, bloklash, xabar yozish, Excel) ·
  **💰 Sotuvlar** (daromad, holatlar, adminlar statistikasi, kutilayotganlar, Excel) · **📢 Xabar yuborish**

**Havola turlari**
- `Doimiy havola` — sozlamalarda kiritilgan link (Google Drive, sayt...)
- `Bir martalik` (tavsiya) — yopiq kanalga **1 kishilik, 24 soatlik** taklif havolasi; boshqaga uzatilsa ishlamaydi.
  Bot kanalda admin bo'lishi va «Foydalanuvchilarni taklif qilish» huquqiga ega bo'lishi kerak.

## Tez ishga tushirish (Windows / Mac / Linux, Docker bilan)

1. [Docker Desktop](https://www.docker.com/products/docker-desktop/) o'rnating.
2. [@BotFather](https://t.me/BotFather) da bot yarating → token oling. O'z ID ingizni [@userinfobot](https://t.me/userinfobot) dan bilib oling.
3. Papkada `.env.example` dan nusxa olib `.env` yarating va to'ldiring:
   ```
   BOT_TOKEN=...
   OWNER_ID=...
   POSTGRES_PASSWORD=kuchli_parol
   MODE=polling
   ```
4. Ishga tushiring:
   ```bash
   docker compose up -d --build
   docker compose logs -f bot
   ```
5. Botga `/start`, keyin `/admin` → **⚙️ Sozlamalar** da karta raqami, narx va havolani kiriting.

Boshqa adminlar: avval ular botga `/start` bosadi, keyin siz **⚙️ Sozlamalar → 👮 Adminlar → ➕** orqali qo'shasiz.

## Serverga joylash (webhook, yuqori yuklama)

VPS (Ubuntu, 2+ vCPU, 2+ GB RAM), domen va A-yozuv kerak.

```bash
# 1) SSL sertifikat (bir marta)
sudo apt install certbot && sudo certbot certonly --standalone -d bot.example.uz

# 2) .env
MODE=webhook
DOMAIN=bot.example.uz
WEBHOOK_URL=https://bot.example.uz
WEBHOOK_SECRET=$(openssl rand -hex 32)
WEB_WORKERS=2          # = CPU yadrolari soni

# 3) ishga tushirish (nginx bilan)
docker compose --profile webhook up -d --build
```

Yangilash: `git pull && docker compose --profile webhook up -d --build` (to'xtash bir necha soniya; Telegram update'larni kutib, qayta yuboradi).
Zaxira nusxa har kuni 03:00 da `./backups/` ga yoziladi (14 kun saqlanadi). Tiklash:
`gunzip -c backups/bot_YYYYMMDD_0300.sql.gz | docker compose exec -T postgres psql -U bot bot`.

## Docker'siz lokal ishga tushirish

PostgreSQL 16 va Redis 7 kerak (Windows'da Redis uchun eng osoni — `docker run -p 6379:6379 redis:7`).
```bash
python -m venv .venv && .venv\Scripts\activate        # Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
# .env ga DATABASE_URL va REDIS_URL yozing
alembic upgrade head
python -m app
```

## Arxitektura

```
Telegram ──HTTPS──► Nginx ──► bot worker 1..N (aiogram 3, uvloop, stateless)
                                   │                │
                               PostgreSQL         Redis
                         (users, payments,   (FSM, sozlamalar keshi,
                          settings, audit)    adminlar, rate-limit, UI)
```

| Yechim | Nima uchun |
|---|---|
| Stateless worker'lar | Holat faqat Redis/Postgres'da → `WEB_WORKERS=N` bilan gorizontal kengayadi |
| Webhook + `handle_in_background` | Telegram'ga darhol 200, sekin so'rov boshqalarni kutdirmaydi |
| Bitta Redis pipeline middleware'da | Admin/ban tekshiruvi, anti-flood, faollik — 1 ta round-trip |
| Atomik `UPDATE … WHERE status='pending'` | Bir nechta admin bir vaqtda bossa ham faqat bittasi yutadi |
| Havola tranzaksiyadan **oldin** yaratiladi | Tarmoq chaqiruvi paytida DB ulanishi band qilinmaydi; tasdiq+havola+xaridor bitta tranzaksiyada |
| Qisman unique index | Bitta userda bir vaqtda faqat 1 ta kutilayotgan to'lov (DB darajasida kafolat) |
| `BlockingConnectionPool` (Redis) | Cho'qqida xato bermaydi, bo'sh ulanishni kutadi |
| Fon vazifalari | Adminlarga tarqatish, broadcast (25 xabar/s), eslatmalar — handler'ni ushlamaydi |
| 429 avtomatik qayta urinish | Telegram flood-limit'ida xabar yo'qolmaydi |

Papkalar: `app/handlers` (Telegram) → `app/services` (biznes mantiq) → `app/db/repositories` (SQL).
Matnlar: `app/texts/uz.py`. Sozlamalar: `app/config.py`.

## Testlar va yuklama testi

```bash
pip install -r requirements-dev.txt
pytest                               # 26 ta test, haqiqiy Postgres+Redis kerak (TEST_DATABASE_URL)
python -m loadtest.bench --users 500 --ramp 10 --think 1 3 --procs 2
```

Yuklama testi haqiqiy dispatcher, PostgreSQL va Redis bilan ishlaydi; Telegram API soxta, lekin har chaqiruvga 50 ms kechikish qo'shiladi.
Natijalar (2 vCPU server, Postgres va Redis ham shu serverda):

| Ssenariy | p50 | p95 | Xato | Natija |
|---|---|---|---|---|
| **500 user** 10 s ichida kiradi, 2 worker | 130 ms | **242 ms** | 0 | 500/500 tasdiq, 500 havola, dublikat yo'q ✅ |
| 500 user — hammasi **bir lahzada**, 2 worker | 1.6 s | 3.3 s | 0 | ✅ (eng og'ir holat) |
| 1000 user 10 s ichida, 2 worker | 1.3 s | 4.9 s | 0 | ✅ — 1000+ uchun 4 vCPU va `WEB_WORKERS=4` tavsiya |
| 2 admin har bir to'lovni bir vaqtda tasdiqlaydi | | | 0 | har biri faqat 1 marta ✅ |

---

# Русская версия

Бот продаж и приёма оплаты по ТЗ (`TZ_tg_sale_bot.md`).

**Пользователь:** `/start` (ID, имя, username сохраняются автоматически) → описание продукта → **🛒 Купить** → реквизиты карты →
отправка чека (фото или JPG/PNG/PDF) → «Принято, ссылка придёт в течение 1 часа» → после подтверждения ссылка приходит автоматически.
Чат не засоряется: у бота всегда одно сообщение-«экран», которое редактируется; лишние сообщения удаляются.

**Админ (`/admin`):** чек приходит всем админам с кнопками **✅ Подтвердить / ❌ Отклонить** (причины на выбор или свой текст).
Даже при одновременном нажатии двумя админами ссылка отправляется ровно один раз, решение отображается у всех.
Нижнее меню: **⚙️ Настройки** (карта, владелец, цена, текст, фото, тип ссылки, канал, вкл/выкл продаж, админы),
**👥 Пользователи** (статистика, поиск, список, бан, сообщение, Excel), **💰 Продажи** (выручка, статусы, по админам, ожидающие, Excel),
**📢 Рассылка**. Напоминание о непроверенных чеках через 50 минут, пометка повторно использованных чеков.

**Запуск:** установить Docker → создать `.env` из `.env.example` (`BOT_TOKEN`, `OWNER_ID`, `POSTGRES_PASSWORD`) →
`docker compose up -d --build`. Для сервера: `MODE=webhook`, домен + SSL (certbot), `WEB_WORKERS` = число ядер,
`docker compose --profile webhook up -d --build`. Бэкап БД — ежедневно в 03:00 в `./backups/`.

**Нагрузка:** 500 одновременных пользователей — p95 = 242 мс при 2 воркерах на 2 vCPU, 0 ошибок, 500/500 подтверждений без дублей.
Для 1000+ пользователей — 4 vCPU и `WEB_WORKERS=4`. Тесты: `pytest` (26 тестов), нагрузочный тест: `python -m loadtest.bench`.
