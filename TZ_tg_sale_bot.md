# TEXNIK TOPSHIRIQ / ТЕХНИЧЕСКОЕ ЗАДАНИЕ
## Telegram savdo va to'lov boti — "Yangi o'zbek kirill alifbosiga o'tkazuvchi dastur"
## Telegram-бот для продаж и приёма оплаты — «Программа конвертации в новый узбекский кириллический алфавит»

| Parametr / Параметр | Qiymat / Значение |
|---|---|
| Hujjat versiyasi / Версия документа | 1.0 |
| Sana / Дата | 04.11.2026 |
| Til / Язык | O'zbekcha (1-qism) · Русский (2-часть) |
| Yuklama talabi / Требование к нагрузке | ≥ 500 bir vaqtdagi foydalanuvchi / ≥ 500 одновременных пользователей, javob / ответ ≤ 1 s |

---

## MUNDARIJA / СОДЕРЖАНИЕ

**1-QISM. O'ZBEKCHA**
1. Loyiha maqsadi
2. Atamalar
3. Texnologiyalar steki
4. Arxitektura
5. Foydalanuvchi oqimi (user flow)
6. "Toza chat" mexanizmi
7. Chekni qabul qilish va adminlarga yuborish
8. Tasdiqlash / rad etish
9. Admin panel
10. Ma'lumotlar bazasi
11. Yuqori yuklama va tezlik (500+ foydalanuvchi)
12. Xavfsizlik
13. Xatolarni boshqarish va loglash
14. Loyiha tuzilmasi (papkalar)
15. Deploy (serverga joylash)
16. Bot matnlari (shablonlar)
17. Qabul qilish mezonlari
18. Ish bosqichlari

**2-ЧАСТЬ. РУССКИЙ** — разделы 1–18 в том же порядке.

---
---

# 1-QISM. O'ZBEKCHA

## 1. Loyiha maqsadi

Telegram bot raqamli mahsulotni — **yangi o'zbek kirill alifbosiga o'tkazuvchi dastur**ni — sotadi. Bot:

1. `/start` bosilganda foydalanuvchining Telegram ID, ismi, familiyasi va username'ini avtomatik saqlaydi.
2. Dastur haqida qisqa ma'lumot beradi, ostida **«🛒 Sotib olish»** tugmasi bo'ladi.
3. Tugma bosilganda karta raqami, karta egasi, to'lov summasi va «To'lovni qiling va chek (skrinshot yoki fayl)ni botga yuboring» degan yozuvni chiqaradi.
4. Chek kelgach uni **barcha adminlarga** yuboradi, foydalanuvchiga esa: *«Qabul qilindi. Chek tekshirilib, 1 soat ichida havola yuboriladi»* deb yozadi.
5. Admin **«✅ Tasdiqlash»** yoki **«❌ Rad etish»** tugmasini bosadi. Tasdiqlansa, foydalanuvchiga havola avtomatik yuboriladi.
6. Chat to'lib ketmasligi uchun bot eski xabarlarini o'chiradi yoki tahrirlaydi (edit), yangisini ketma-ket qo'shib ketmaydi.
7. Adminlar uchun panel bor: pastki klaviaturada **⚙️ Sozlamalar**, **👥 Userlar**, **💰 Sotuvlar** tugmalari.
8. Kamida **500 kishi bir vaqtda** foydalanganda ham qotmaydi.

## 2. Atamalar

| Atama | Ma'nosi |
|---|---|
| User | Botdan mahsulot sotib oluvchi oddiy foydalanuvchi |
| Admin | To'lovlarni tekshiradigan, sozlamalarni o'zgartiradigan shaxs |
| Super-admin | Adminlarni qo'shish/o'chirish huquqi bor egasi (`.env` dagi `OWNER_ID`) |
| Chek | To'lov tasdig'i: rasm (photo) yoki fayl (document: jpg/png/pdf) |
| Buyurtma (payment) | Bitta chek bo'yicha yozuv: `pending` → `approved` / `rejected` |
| Havola | Tasdiqdan keyin beriladigan link (yopiq kanalga bir martalik taklif yoki yuklab olish havolasi) |
| FSM | Finite State Machine — foydalanuvchi qaysi bosqichdaligini saqlovchi holat mashinasi |

## 3. Texnologiyalar steki

| Qatlam | Texnologiya | Nima uchun |
|---|---|---|
| Til | **Python 3.12** | Asinxronlik, keng ekotizim |
| Bot freymvork | **aiogram 3.x** | To'liq asinxron, router, middleware, FSM o'rnatilgan |
| Event loop | **uvloop** | asyncio'dan 2–4 barobar tezroq |
| Ma'lumotlar bazasi | **PostgreSQL 16** | Ishonchli, tranzaksiyalar, parallel yozish |
| DB drayver/ORM | **SQLAlchemy 2.0 (async) + asyncpg** | Eng tez async Postgres drayveri, connection pool |
| Migratsiyalar | **Alembic** | Sxemani versiyalash |
| Kesh / FSM / navbat | **Redis 7** | FSM holatlari, sozlamalar keshi, rate-limit, oxirgi xabar ID lari |
| Fon vazifalari | **asyncio task + Redis navbat** (ixtiyoriy: **arq**) | Adminlarga tarqatish, ommaviy xabar (broadcast) |
| Rejim | **Webhook** (prod), Polling (dev) | Webhook — kam kechikish, gorizontal kengayish |
| HTTP server | **aiohttp** (aiogram ichida) + **Nginx** (reverse proxy, SSL) | |
| Konteyner | **Docker + docker-compose** | Bir buyruq bilan ishga tushirish |
| Konfiguratsiya | **pydantic-settings**, `.env` | Maxfiy ma'lumotlar kodda emas |
| Eksport | **openpyxl** | Userlar va sotuvlarni Excelga chiqarish |
| Monitoring | **Sentry** (xatolar), loglar JSON formatda | |

## 4. Arxitektura

```mermaid
flowchart LR
    TG[Telegram Bot API] -- HTTPS webhook --> NG[Nginx + SSL]
    NG --> APP1[Bot instance 1<br/>aiogram + uvloop]
    NG --> APP2[Bot instance 2<br/>ixtiyoriy]
    APP1 & APP2 --> RD[(Redis<br/>FSM · kesh · rate-limit · navbat)]
    APP1 & APP2 --> PG[(PostgreSQL<br/>users · payments · settings)]
    APP1 & APP2 --> WK[Worker<br/>broadcast · admin fan-out · eslatmalar]
    WK --> RD
    WK --> PG
    WK -- sendMessage --> TG
```

**Asosiy tamoyillar:**

1. **Stateless bot instansiyalari** — hech qanday holat xotirada (RAM) saqlanmaydi, hammasi Redis/Postgres'da. Shuning uchun kerak bo'lsa 2–3 ta instansiya ishga tushirish mumkin.
2. **Handler tez javob beradi** — og'ir ishlar (10 ta adminga yuborish, broadcast) fon vazifasiga beriladi; handler 100 ms ichida tugaydi.
3. **Qatlamlar:** `handlers` (Telegram bilan ishlash) → `services` (biznes mantiq) → `repositories` (DB so'rovlari). Handler ichida SQL yozilmaydi.
4. **Idempotentlik** — bir xil callback ikki marta kelsa ham natija bitta (masalan, to'lov ikki marta tasdiqlanmaydi).

## 5. Foydalanuvchi oqimi (user flow)

```mermaid
stateDiagram-v2
    [*] --> Start: /start
    Start --> Info: user saqlanadi (UPSERT)
    Info --> PaymentDetails: «🛒 Sotib olish»
    PaymentDetails --> Info: «⬅️ Orqaga»
    PaymentDetails --> WaitingReceipt: holat = kutilmoqda
    WaitingReceipt --> Pending: rasm/fayl yuborildi
    WaitingReceipt --> WaitingReceipt: matn/noto'g'ri fayl → ogohlantirish
    Pending --> Approved: admin ✅
    Pending --> Rejected: admin ❌
    Rejected --> PaymentDetails: «🔄 Qayta yuborish»
    Approved --> [*]: havola yuborildi
```

### 5.1. `/start`
- Bot `users` jadvaliga **UPSERT** qiladi (`INSERT ... ON CONFLICT (telegram_id) DO UPDATE`): `telegram_id`, `first_name`, `last_name`, `username`, `language_code`, `created_at`, `last_active_at`.
- Agar foydalanuvchi bloklangan bo'lsa (`is_banned = true`) — javob berilmaydi.
- Agar foydalanuvchi mahsulotni **allaqachon sotib olgan** bo'lsa — ma'lumot o'rniga «Siz allaqachon xarid qilgansiz» va havolani qayta olish tugmasi chiqadi.
- Deep-link qo'llab-quvvatlanadi: `/start ref_123` → `users.source = 'ref_123'` (reklama manbasini kuzatish uchun).
- Xabar: mahsulot rasmi (ixtiyoriy) + qisqa tavsif + **«🛒 Sotib olish»** inline tugmasi.

### 5.2. «Sotib olish»
- Yangi xabar yuborilmaydi — **mavjud xabar tahrirlanadi** (`edit_message_text` / `edit_message_caption`).
- Ko'rsatiladi: karta raqami (bosilganda nusxa olinadigan `<code>` formatda), karta egasi, summa, ko'rsatma.
- Tugmalar: **«⬅️ Orqaga»**.
- FSM holati: `BuyStates.waiting_receipt`.
- Agar foydalanuvchida `pending` holatdagi to'lov bo'lsa — «Chekingiz tekshirilmoqda, iltimos kuting» chiqadi, yangi chek qabul qilinmaydi.
- Agar sozlamalarda sotuv o'chirilgan bo'lsa (`sales_enabled = false`) — «Sotuv vaqtincha to'xtatilgan».

### 5.3. Chek yuborish
- Qabul qilinadi: `photo`, `document` (mime: `image/jpeg`, `image/png`, `image/webp`, `application/pdf`), hajmi ≤ 10 MB.
- Matn, stiker, ovozli xabar va boshqalar → foydalanuvchi xabari o'chiriladi, bot xabari «Iltimos, chekni rasm yoki fayl ko'rinishida yuboring» deb tahrirlanadi.
- Muvaffaqiyatli bo'lsa: 7-bo'limga qarang.

## 6. "Toza chat" mexanizmi

Maqsad: foydalanuvchi chatida **bir vaqtda faqat 1 ta bot xabari** (asosiy "ekran") turishi.

| Qoida | Amalga oshirish |
|---|---|
| Bot har bir foydalanuvchi uchun oxirgi xabar ID sini saqlaydi | Redis: `ui:last_msg:{user_id}` → `message_id` (TTL 48 soat) |
| Tugma bosilganda | Yangi xabar emas, `edit_message_*` bilan o'sha xabar o'zgartiriladi |
| Holat to'liq o'zgarsa (masalan, chek qabul qilindi) | Eski xabar `delete_message`, yangisi yuboriladi va ID saqlanadi |
| Foydalanuvchining `/start` buyrug'i va noto'g'ri xabarlari | Bot ularni o'chiradi |
| Chek rasmi | **O'chirilmaydi** (foydalanuvchida dalil sifatida qoladi) |
| 48 soatdan eski xabar | Telegram o'chirishga ruxsat bermaydi → xato jim ushlanadi, yangi xabar yuboriladi |
| `message is not modified` xatosi | Jim e'tiborsiz qoldiriladi |

Bu logika bitta yordamchi funksiyada bo'ladi: `ui.render(user_id, text, keyboard, media=None)` — u o'zi edit qilishni yoki o'chirib-yangidan yuborishni tanlaydi.

## 7. Chekni qabul qilish va adminlarga yuborish

```mermaid
sequenceDiagram
    participant U as User
    participant B as Bot
    participant DB as PostgreSQL
    participant R as Redis
    participant A as Adminlar (N ta)
    U->>B: rasm / fayl
    B->>R: rate-limit tekshiruvi
    B->>DB: pending bormi? file_unique_id takrormi?
    B->>DB: INSERT payments (status=pending)
    B->>U: «✅ Qabul qilindi, 1 soat ichida havola yuboriladi»
    B-->>A: fon vazifasi: har bir adminga chek + [✅ Tasdiqlash] [❌ Rad etish]
    B->>DB: admin_messages (payment_id, admin_id, message_id)
```

**Batafsil:**
1. **Takroriy chek tekshiruvi:** `file_unique_id` bo'yicha — bir xil rasm avval boshqa to'lovda ishlatilgan bo'lsa, adminga ⚠️ «Bu chek avval #123 to'lovda yuborilgan» degan belgi bilan boradi.
2. `payments` ga yozuv: `user_id`, `amount` (sozlamalardagi joriy summa — keyin summa o'zgarsa ham tarix buzilmaydi), `file_id`, `file_unique_id`, `file_type`, `status='pending'`, `created_at`.
3. Foydalanuvchiga xabar va FSM holati tozalanadi.
4. **Adminlarga tarqatish (fan-out)** — fon vazifasida, `asyncio.Semaphore(10)` bilan parallel, `TelegramRetryAfter` bo'lsa kutib qayta urinadi. Har bir admin xabari:
   ```
   🧾 Yangi to'lov #1024
   👤 Ism: Javohir Akramov
   🆔 ID: 123456789  ·  @username
   💰 Summa: 50 000 so'm
   🕒 04.11.2026 11:42
   [✅ Tasdiqlash] [❌ Rad etish]
   ```
   callback_data: `pay:ok:1024`, `pay:no:1024` (aiogram `CallbackData` fabrikasi orqali).
5. Har bir adminga yuborilgan xabar ID si `admin_messages` jadvaliga yoziladi — keyin barcha adminlarda natija ko'rsatish uchun.
6. **SLA nazorati:** 50 daqiqa ichida ko'rib chiqilmagan to'lovlar haqida worker adminlarga eslatma yuboradi («⏰ 3 ta to'lov 50 daqiqadan beri kutmoqda»).

## 8. Tasdiqlash / rad etish

### 8.1. Poyga holatidan himoya (race condition)
Bir nechta admin bir vaqtda tugma bossa — faqat **birinchisi** amalga oshadi:
```sql
UPDATE payments
SET status = 'approved', reviewed_by = :admin_id, reviewed_at = now()
WHERE id = :payment_id AND status = 'pending'
RETURNING user_id;
```
Agar qator qaytmasa → adminga `answer_callback_query("Bu to'lov allaqachon ko'rib chiqilgan", show_alert=True)`.

### 8.2. Tasdiqlash
1. Havola yaratiladi (sozlamaga qarab):
   - **A varianti (tavsiya):** yopiq kanal/guruhga **bir martalik taklif havolasi** — `create_chat_invite_link(chat_id, member_limit=1, expire_date=+24 soat, name="pay#1024")`. Havola boshqalarga tarqatilsa ham ishlamaydi.
   - **B varianti:** sozlamalardagi doimiy havola (Google Drive, sayt va h.k.).
2. Foydalanuvchiga: «🎉 To'lovingiz tasdiqlandi! Dasturni yuklab olish havolasi: …». Foydalanuvchi botni bloklagan bo'lsa → `users.is_blocked_bot = true`, adminga xabar.
3. `users.has_purchased = true`.
4. **Barcha adminlarda** o'sha xabar tahrirlanadi: tugmalar olib tashlanadi, ostiga «✅ Tasdiqladi: @admin_name, 11:50» yoziladi.

### 8.3. Rad etish
1. Admin ❌ bossa, tayyor sabablar tugmalari chiqadi:
   - «Summa noto'g'ri» · «Chek o'qilmaydi» · «To'lov tushmagan» · «Soxta chek» · «✍️ Boshqa sabab (yozish)» · «⬅️ Bekor qilish»
2. Sabab tanlangach, xuddi 8.1 dagi atomik `UPDATE` (`status='rejected'`, `reject_reason`).
3. Foydalanuvchiga: «❌ To'lovingiz rad etildi. Sabab: … » + **«🔄 Chekni qayta yuborish»** tugmasi.
4. Barcha adminlarda xabar «❌ Rad etdi: @admin_name — sabab» deb yangilanadi.
5. «Soxta chek» tanlansa — ixtiyoriy ravishda «🚫 Userni bloklash» tugmasi taklif qilinadi.

## 9. Admin panel

Kirish: `/admin` buyrug'i (faqat adminlar uchun; boshqalarga javob berilmaydi). Pastda **ReplyKeyboard**:

```
[ ⚙️ Sozlamalar ] [ 👥 Userlar ] [ 💰 Sotuvlar ]
[ 📢 Xabar yuborish ] [ 🏠 Chiqish ]
```
(«Xabar yuborish» — tavsiya etiladigan qo'shimcha funksiya.)

Admin panel ichidagi menyular ham **bitta xabarni tahrirlash** tamoyilida ishlaydi.

### 9.1. ⚙️ Sozlamalar
| Sozlama | Tavsif | Tekshiruv |
|---|---|---|
| 💳 Karta raqami | 16 raqam | faqat raqam, 16 ta, Luhn tekshiruvi |
| 👤 Karta egasi | Ism familiya | 3–64 belgi |
| 💰 Narx | so'mda | musbat butun son |
| 📝 Mahsulot matni | /start dagi tavsif (HTML) | ≤ 1024 belgi (rasm bo'lsa), aks holda ≤ 4096 |
| 🖼 Mahsulot rasmi | ixtiyoriy | photo |
| 🔗 Havola turi | bir martalik invite / doimiy link | |
| 📣 Kanal ID | A variant uchun | bot kanalda admin ekanini tekshirish |
| 🔗 Doimiy havola | B variant uchun | URL formati |
| 👮 Adminlar | qo'shish (ID orqali) / o'chirish / ro'yxat | faqat super-admin |
| 🔌 Sotuv yoqilgan/o'chirilgan | | |

- Har bir o'zgarish: oldingi qiymat ko'rsatiladi → admin yangisini yuboradi → «✅ Saqlash / ❌ Bekor qilish».
- Sozlamalar `settings` jadvalida, Redis'da keshlanadi; o'zgarganda kesh darhol tozalanadi.
- Har bir o'zgarish `audit_log` ga yoziladi (kim, qachon, eski → yangi qiymat).

### 9.2. 👥 Userlar
- Statistika: jami · bugun · 7 kun · 30 kun · xarid qilganlar · botni bloklaganlar · konversiya (%).
- 🔍 Qidirish: ID yoki @username bo'yicha → user kartochkasi (ma'lumotlar, to'lovlar tarixi, tugmalar: «🚫 Bloklash / ✅ Blokdan chiqarish», «🔗 Havolani qayta yuborish», «✉️ Xabar yozish»).
- 📄 Ro'yxat: sahifalab (10 tadan, ◀️ ▶️), oxirgi qo'shilganlar birinchi.
- 📥 Excel eksport: barcha userlar `.xlsx` fayl sifatida (fon vazifasida yaratiladi).

### 9.3. 💰 Sotuvlar
- Daromad va soni: bugun · hafta · oy · jami.
- Holatlar bo'yicha: ⏳ kutilmoqda · ✅ tasdiqlangan · ❌ rad etilgan.
- ⏳ **Kutilayotganlar ro'yxati** — har biri bosilsa chek qayta ochiladi va tasdiqlash/rad etish tugmalari chiqadi (admin xabarni yo'qotib qo'ysa ham).
- Adminlar bo'yicha: kim nechta to'lovni ko'rib chiqdi, o'rtacha ko'rib chiqish vaqti.
- 📥 Excel eksport (sana oralig'i bilan).

### 9.4. 📢 Xabar yuborish (broadcast) — qo'shimcha
- Admin matn/rasm yuboradi → ko'rib chiqish → «Hammaga / Faqat xaridorlarga / Xarid qilmaganlarga» → tasdiqlash.
- Worker orqali sekundiga **≤ 25 xabar** (Telegram limiti 30/s), `RetryAfter` ni hurmat qiladi.
- Natija: yuborildi / bloklagan / xato soni.

## 10. Ma'lumotlar bazasi

```mermaid
erDiagram
    users ||--o{ payments : "qiladi"
    payments ||--o{ admin_messages : "yuboriladi"
    admins ||--o{ payments : "ko'rib chiqadi"
    admins ||--o{ audit_log : "yozadi"
```

```sql
CREATE TABLE users (
    telegram_id      BIGINT PRIMARY KEY,
    first_name       VARCHAR(128) NOT NULL,
    last_name        VARCHAR(128),
    username         VARCHAR(64),
    language_code    VARCHAR(8),
    source           VARCHAR(64),             -- deep-link manbasi
    has_purchased    BOOLEAN NOT NULL DEFAULT false,
    is_banned        BOOLEAN NOT NULL DEFAULT false,
    is_blocked_bot   BOOLEAN NOT NULL DEFAULT false,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_active_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_users_created_at ON users (created_at);
CREATE INDEX ix_users_username   ON users (lower(username));

CREATE TYPE payment_status AS ENUM ('pending', 'approved', 'rejected');

CREATE TABLE payments (
    id               BIGSERIAL PRIMARY KEY,
    user_id          BIGINT NOT NULL REFERENCES users(telegram_id),
    amount           INTEGER NOT NULL,
    file_id          VARCHAR(256) NOT NULL,
    file_unique_id   VARCHAR(64)  NOT NULL,
    file_type        VARCHAR(16)  NOT NULL,   -- photo | document
    status           payment_status NOT NULL DEFAULT 'pending',
    reviewed_by      BIGINT REFERENCES admins(telegram_id),
    reviewed_at      TIMESTAMPTZ,
    reject_reason    VARCHAR(256),
    invite_link      VARCHAR(256),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_payments_status_created ON payments (status, created_at);
CREATE INDEX ix_payments_user           ON payments (user_id);
CREATE INDEX ix_payments_file_unique    ON payments (file_unique_id);
-- Bitta userda bir vaqtda faqat 1 ta pending:
CREATE UNIQUE INDEX ux_payments_one_pending ON payments (user_id) WHERE status = 'pending';

CREATE TABLE admin_messages (
    payment_id   BIGINT NOT NULL REFERENCES payments(id) ON DELETE CASCADE,
    admin_id     BIGINT NOT NULL,
    message_id   BIGINT NOT NULL,
    PRIMARY KEY (payment_id, admin_id)
);

CREATE TABLE admins (
    telegram_id  BIGINT PRIMARY KEY,
    name         VARCHAR(128),
    is_owner     BOOLEAN NOT NULL DEFAULT false,
    added_by     BIGINT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE settings (
    key          VARCHAR(64) PRIMARY KEY,
    value        TEXT NOT NULL,
    updated_by   BIGINT,
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE audit_log (
    id           BIGSERIAL PRIMARY KEY,
    admin_id     BIGINT NOT NULL,
    action       VARCHAR(64) NOT NULL,   -- approve, reject, setting_change, ban ...
    payload      JSONB,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Redis kalitlari:**

| Kalit | Ma'nosi | TTL |
|---|---|---|
| `fsm:{bot}:{chat}:{user}:state/data` | aiogram FSM (RedisStorage) | 24 soat |
| `ui:last_msg:{user_id}` | oxirgi bot xabari ID | 48 soat |
| `cache:settings` | barcha sozlamalar (hash) | 10 daqiqa + o'zgarganda o'chiriladi |
| `cache:admins` | admin ID lari (set) | 10 daqiqa + o'zgarganda o'chiriladi |
| `rl:{user_id}` | rate-limit hisoblagichi | 1–5 s |
| `seen:user:{id}` | `last_active_at` ni har xabarda emas, 5 daqiqada 1 marta yangilash | 5 daqiqa |

## 11. Yuqori yuklama va tezlik (500+ foydalanuvchi)

### 11.1. Maqsadli ko'rsatkichlar
| Ko'rsatkich | Talab |
|---|---|
| Bir vaqtdagi faol foydalanuvchi | ≥ 500 (zaxira bilan 2 000 gacha) |
| Handler ishlash vaqti (p95) | ≤ 150 ms |
| Foydalanuvchi uchun javob (p95) | ≤ 1 s |
| Kiruvchi update oqimi | ≥ 100 update/s barqaror |
| Xatolar | < 0,1 % |

### 11.2. Choralar
1. **Webhook rejimi** — Telegram update'larni o'zi yuboradi; polling'dagi kechikish yo'q. `secret_token` bilan himoyalangan.
2. **To'liq asinxronlik** — hech qanday bloklovchi chaqiruv yo'q (`requests`, `time.sleep`, sinxron DB drayverlari taqiqlanadi). Excel yaratish kabi CPU ishlari `asyncio.to_thread` da.
3. **Parallel update qayta ishlash** — aiogram'da `handle_in_background=True` (webhook), bitta sekin so'rov boshqalarni to'xtatmaydi.
4. **Connection pool** — Postgres: `pool_size=20, max_overflow=10, pool_pre_ping=True`; Redis: pool 50.
5. **Kesh** — sozlamalar va adminlar ro'yxati har so'rovda DB dan o'qilmaydi (Redis + 30 s lokal in-memory kesh).
6. **Yozuvlarni kamaytirish** — `last_active_at` har xabarda emas, 5 daqiqada 1 marta; `/start` da bitta UPSERT so'rov.
7. **Fon vazifalari** — adminlarga fan-out, broadcast, eslatmalar, eksport — handlerni ushlab turmaydi.
8. **Telegram limitlarini hurmat qilish** — global ~30 xabar/s, bitta chatga ~1 xabar/s. aiogram session'ga `TelegramRetryAfter` uchun avtomatik qayta urinish middleware'i; broadcast token-bucket bilan 25/s.
9. **Rate-limit (anti-flood)** — userga: sekundiga 2 ta harakatdan ko'p bo'lsa e'tiborsiz qoldiriladi; chek yuborish — daqiqasiga 3 tadan ko'p emas.
10. **Indekslar** — barcha filtr va saralash ustunlariga (10-bo'lim).
11. **Gorizontal kengayish** — stateless bo'lgani uchun Nginx ortida 2+ instansiya.
12. **Yuklama testi** — topshirishdan oldin **Locust** yoki maxsus skript bilan webhook endpoint'ga soxta update'lar yuborib, 500 bir vaqtdagi foydalanuvchi × 5 daqiqa ssenariysi sinovdan o'tkaziladi; natija hisobot sifatida topshiriladi.

### 11.3. Server talablari (minimal)
| Resurs | 500 user | 2 000+ user |
|---|---|---|
| CPU | 2 vCPU | 4 vCPU |
| RAM | 2 GB | 4 GB |
| Disk | 20 GB SSD | 40 GB SSD |
| OS | Ubuntu 22.04/24.04 | |

## 12. Xavfsizlik

1. **Token va parollar** faqat `.env` da, repozitoriyga tushmaydi (`.gitignore`).
2. **Admin tekshiruvi** — middleware orqali: admin router'idagi har bir handler va callback faqat `cache:admins` dagi ID lar uchun ishlaydi. Callback'da ham qayta tekshiriladi (callback_data'ni soxtalashtirishdan himoya).
3. **Webhook** — `X-Telegram-Bot-Api-Secret-Token` sarlavhasi tekshiriladi; Nginx faqat Telegram IP diapazonlaridan (149.154.160.0/20, 91.108.4.0/22) qabul qiladi.
4. **SQL injection** — faqat ORM/parametrli so'rovlar.
5. **HTML injection** — foydalanuvchi ismi admin xabarlarida `html.escape` qilinadi.
6. **Soxta cheklar** — `file_unique_id` takror tekshiruvi; admin pul kartaga haqiqatan tushganini bank ilovasida tekshirishi shart (bot buni avtomatik qilmaydi).
7. **Havola sizib chiqishi** — bir martalik invite link (`member_limit=1`, 24 soat).
8. **Zaxira nusxa** — Postgres har kuni `pg_dump`, 14 kun saqlanadi, ixtiyoriy ravishda super-adminga Telegram'da fayl sifatida.
9. **Audit** — barcha admin harakatlari `audit_log` da.

## 13. Xatolarni boshqarish va loglash

| Holat | Harakat |
|---|---|
| Foydalanuvchi botni bloklagan (`Forbidden`) | `is_blocked_bot=true`, xato emas |
| `message is not modified` | jim e'tiborsiz |
| `message to delete not found` / 48 soatdan eski | jim e'tiborsiz |
| `RetryAfter` | ko'rsatilgan vaqt kutib, qayta urinish (maks 3) |
| DB / Redis uzilishi | qayta ulanish, foydalanuvchiga «Texnik nosozlik, birozdan so'ng urinib ko'ring», Sentry'ga xabar |
| Kutilmagan xato | global error handler → log + Sentry + super-adminga qisqa xabar (spamsiz: 5 daqiqada 1 marta) |

Loglar: JSON formatda, `INFO` darajasi, har update uchun `update_id`, `user_id`, handler nomi, ishlash vaqti (ms). Log fayllar aylanadi (rotation), 7 kun saqlanadi.

## 14. Loyiha tuzilmasi

```
tg-sale-bot/
├── app/
│   ├── __main__.py              # ishga tushirish (webhook/polling)
│   ├── config.py                # pydantic-settings
│   ├── bot.py                   # Bot, Dispatcher, router'larni ulash
│   ├── handlers/
│   │   ├── user/
│   │   │   ├── start.py
│   │   │   ├── buy.py
│   │   │   └── receipt.py
│   │   └── admin/
│   │       ├── panel.py
│   │       ├── review.py        # tasdiqlash / rad etish
│   │       ├── settings.py
│   │       ├── users.py
│   │       ├── sales.py
│   │       └── broadcast.py
│   ├── keyboards/               # inline va reply klaviaturalar
│   ├── callbacks.py             # CallbackData fabrikalari
│   ├── states.py                # FSM holatlari
│   ├── middlewares/
│   │   ├── db_session.py
│   │   ├── throttling.py
│   │   ├── admin_filter.py
│   │   └── user_activity.py
│   ├── services/
│   │   ├── payment_service.py
│   │   ├── notify_service.py    # adminlarga fan-out
│   │   ├── link_service.py      # invite link yaratish
│   │   ├── settings_service.py  # kesh bilan
│   │   ├── stats_service.py
│   │   └── ui.py                # "toza chat" render
│   ├── db/
│   │   ├── models.py
│   │   ├── repositories/
│   │   └── session.py
│   ├── worker/
│   │   ├── tasks.py             # broadcast, eslatmalar, eksport
│   │   └── scheduler.py
│   ├── texts/
│   │   ├── uz.py
│   │   └── ru.py                # keyinchalik ruscha interfeys uchun
│   └── utils/
├── migrations/                  # Alembic
├── tests/
├── loadtest/locustfile.py
├── docker-compose.yml
├── Dockerfile
├── nginx/bot.conf
├── .env.example
└── README.md
```

**`.env.example`:**
```
BOT_TOKEN=
OWNER_ID=
WEBHOOK_URL=https://bot.example.uz
WEBHOOK_PATH=/tg/webhook
WEBHOOK_SECRET=
DATABASE_URL=postgresql+asyncpg://bot:pass@postgres:5432/bot
REDIS_URL=redis://redis:6379/0
SENTRY_DSN=
MODE=webhook        # webhook | polling
```

## 15. Deploy

1. VPS (Ubuntu), domen va A-yozuv.
2. `docker compose up -d` — servislar: `bot`, `worker`, `postgres`, `redis`, `nginx` (+ `certbot`).
3. `alembic upgrade head` — konteyner ishga tushganda avtomatik.
4. Bot ishga tushganda `set_webhook(url, secret_token, allowed_updates=[...], drop_pending_updates=False)`.
5. `restart: unless-stopped` — server qayta yonsa bot ham avtomatik ko'tariladi.
6. Postgres va Redis ma'lumotlari Docker volume'larda.
7. Yangilash: `git pull && docker compose up -d --build` — to'xtash ≤ 10 s (Telegram webhook'ni kutib turadi va qayta yuboradi).

## 16. Bot matnlari (shablonlar, sozlamalardan tahrirlanadi)

**Start:**
> 👋 Assalomu alaykum, {ism}!
>
> 🔤 **Yangi o'zbek kirill alifbosiga o'tkazuvchi dastur** — matnlaringizni lotin va eski kirill yozuvidan yangi kirill alifbosiga bir zumda o'tkazadi.
>
> ✅ Tez va aniq o'girish
> ✅ Word va matn fayllari bilan ishlaydi
> ✅ Internetsiz ishlaydi
>
> 💰 Narxi: {narx} so'm
>
> [🛒 Sotib olish]

*(Mahsulot afzalliklari — namuna; aniq matnni buyurtmachi beradi.)*

**To'lov ma'lumotlari:**
> 💳 **To'lov ma'lumotlari**
>
> Karta raqami: `8600 1234 5678 9012`
> Karta egasi: {karta_egasi}
> Summa: **{narx} so'm**
>
> 📸 To'lovni amalga oshiring va **chek (skrinshot yoki fayl)**ni shu yerga yuboring.
>
> [⬅️ Orqaga]

**Chek qabul qilindi:**
> ✅ Chekingiz qabul qilindi!
> Chek tekshirilib, **1 soat ichida** sizga havola yuboriladi.

**Tasdiqlandi:**
> 🎉 To'lovingiz tasdiqlandi! Xaridingiz uchun rahmat.
> 🔗 Havola: {havola}
> ⚠️ Havola faqat siz uchun va 24 soat amal qiladi.

**Rad etildi:**
> ❌ To'lovingiz rad etildi.
> Sabab: {sabab}
> [🔄 Chekni qayta yuborish]

## 17. Qabul qilish mezonlari

- [ ] `/start` dan keyin user DB da paydo bo'ladi; qayta `/start` dublikat yaratmaydi.
- [ ] Butun xarid jarayonida foydalanuvchi chatida bot xabarlaridan **1 tadan ko'p** turmaydi (chek rasmidan tashqari).
- [ ] Chek **barcha** adminlarga 5 s ichida yetib boradi.
- [ ] 2 admin bir vaqtda «Tasdiqlash» bossa — havola **1 marta** yuboriladi, ikkinchi adminga «allaqachon ko'rib chiqilgan» chiqadi.
- [ ] Tasdiq/rad etishdan keyin barcha adminlardagi xabar yangilanadi.
- [ ] Bir userda bir vaqtda 2 ta `pending` to'lov bo'lmaydi.
- [ ] Sozlamalar o'zgarishi darhol (≤ 1 s) yangi foydalanuvchilarga ko'rinadi.
- [ ] Oddiy user `/admin` va admin callback'lariga kira olmaydi.
- [ ] Yuklama testi: 500 bir vaqtdagi user × 5 daqiqa, p95 ≤ 1 s, xato < 0,1 %.
- [ ] Server qayta yonganda bot avtomatik ishlaydi, ma'lumot va FSM holatlari yo'qolmaydi.
- [ ] Excel eksport to'g'ri ochiladi.
- [ ] Kod: README, `.env.example`, migratsiyalar, asosiy servislar uchun testlar (pytest, ≥ 60 % qamrov).

## 18. Ish bosqichlari

| # | Bosqich | Natija | Taxminiy muddat |
|---|---|---|---|
| 1 | Loyiha karkasi, Docker, DB sxema, migratsiyalar | Bo'sh bot ishga tushadi | 1 kun |
| 2 | User oqimi: start, sotib olish, chek, toza chat | Foydalanuvchi chek yubora oladi | 2 kun |
| 3 | Adminlarga yuborish, tasdiqlash/rad etish, havola | To'liq sotuv sikli | 2 kun |
| 4 | Admin panel: sozlamalar, userlar, sotuvlar, eksport | Panel tayyor | 2–3 kun |
| 5 | Broadcast, eslatmalar, audit, zaxira nusxa | Qo'shimcha funksiyalar | 1–2 kun |
| 6 | Testlar, yuklama testi, optimizatsiya | Hisobot | 1–2 kun |
| 7 | Deploy, hujjatlar, topshirish | Ishlayotgan bot | 1 kun |
| | **Jami** | | **~10–13 ish kuni** |

---
---

# 2-ЧАСТЬ. РУССКИЙ

## 1. Цель проекта

Telegram-бот продаёт цифровой продукт — **программу конвертации текста в новый узбекский кириллический алфавит**. Бот:

1. При нажатии `/start` автоматически сохраняет Telegram ID, имя, фамилию и username пользователя.
2. Показывает краткое описание программы с кнопкой **«🛒 Купить»** (на узбекском — «Sotib olish»).
3. По нажатию выводит номер карты, владельца карты, сумму оплаты и текст «Оплатите и отправьте чек (скриншот или файл) в бот».
4. Получив чек, пересылает его **всем администраторам**, а пользователю пишет: *«Принято. Чек будет проверен, ссылка придёт в течение 1 часа»*.
5. Администратор нажимает **«✅ Подтвердить»** или **«❌ Отклонить»**. После подтверждения пользователь автоматически получает ссылку.
6. Чтобы чат не засорялся, бот удаляет или редактирует свои старые сообщения, а не добавляет новые одно за другим.
7. Для админов есть панель: внизу кнопки **⚙️ Настройки**, **👥 Пользователи**, **💰 Продажи**.
8. Бот не зависает минимум при **500 одновременных пользователях**.

## 2. Термины

| Термин | Значение |
|---|---|
| Пользователь (User) | Покупатель продукта |
| Админ | Проверяет оплаты, меняет настройки |
| Супер-админ | Владелец, может добавлять/удалять админов (`OWNER_ID` в `.env`) |
| Чек | Подтверждение оплаты: фото или файл (jpg/png/pdf) |
| Платёж (payment) | Запись по одному чеку: `pending` → `approved` / `rejected` |
| Ссылка | Выдаётся после подтверждения (одноразовое приглашение в закрытый канал или ссылка на скачивание) |
| FSM | Конечный автомат — хранит, на каком шаге находится пользователь |

## 3. Технологический стек

| Слой | Технология | Почему |
|---|---|---|
| Язык | **Python 3.12** | Асинхронность, большая экосистема |
| Фреймворк | **aiogram 3.x** | Полностью асинхронный, роутеры, middleware, встроенный FSM |
| Event loop | **uvloop** | В 2–4 раза быстрее стандартного asyncio |
| БД | **PostgreSQL 16** | Надёжность, транзакции, параллельная запись |
| Драйвер/ORM | **SQLAlchemy 2.0 (async) + asyncpg** | Самый быстрый async-драйвер Postgres, пул соединений |
| Миграции | **Alembic** | Версионирование схемы |
| Кэш / FSM / очередь | **Redis 7** | Состояния FSM, кэш настроек, rate-limit, ID последних сообщений |
| Фоновые задачи | **asyncio task + очередь в Redis** (опционально **arq**) | Рассылка админам, массовые рассылки |
| Режим | **Webhook** (prod), Polling (dev) | Минимальная задержка, горизонтальное масштабирование |
| HTTP | **aiohttp** (встроен в aiogram) + **Nginx** (reverse proxy, SSL) | |
| Контейнеры | **Docker + docker-compose** | Запуск одной командой |
| Конфигурация | **pydantic-settings**, `.env` | Секреты не в коде |
| Экспорт | **openpyxl** | Выгрузка пользователей и продаж в Excel |
| Мониторинг | **Sentry**, логи в JSON | |

## 4. Архитектура

```mermaid
flowchart LR
    TG[Telegram Bot API] -- HTTPS webhook --> NG[Nginx + SSL]
    NG --> APP1[Инстанс бота 1<br/>aiogram + uvloop]
    NG --> APP2[Инстанс бота 2<br/>опционально]
    APP1 & APP2 --> RD[(Redis<br/>FSM · кэш · rate-limit · очередь)]
    APP1 & APP2 --> PG[(PostgreSQL<br/>users · payments · settings)]
    APP1 & APP2 --> WK[Worker<br/>рассылки · уведомления админам · напоминания]
    WK --> RD
    WK --> PG
    WK -- sendMessage --> TG
```

**Ключевые принципы:**

1. **Stateless-инстансы** — никакого состояния в оперативной памяти, всё в Redis/Postgres. Можно запустить 2–3 инстанса.
2. **Хендлер отвечает быстро** — тяжёлая работа (отправка 10 админам, рассылка) уходит в фон; хендлер завершается за ~100 мс.
3. **Слои:** `handlers` (работа с Telegram) → `services` (бизнес-логика) → `repositories` (запросы к БД). SQL в хендлерах запрещён.
4. **Идемпотентность** — повторный одинаковый callback не меняет результат (платёж не будет подтверждён дважды).

## 5. Пользовательский сценарий (user flow)

```mermaid
stateDiagram-v2
    [*] --> Start: /start
    Start --> Info: пользователь сохранён (UPSERT)
    Info --> PaymentDetails: «🛒 Купить»
    PaymentDetails --> Info: «⬅️ Назад»
    PaymentDetails --> WaitingReceipt: состояние = ожидание чека
    WaitingReceipt --> Pending: отправлено фото/файл
    WaitingReceipt --> WaitingReceipt: текст/неверный файл → предупреждение
    Pending --> Approved: админ ✅
    Pending --> Rejected: админ ❌
    Rejected --> PaymentDetails: «🔄 Отправить заново»
    Approved --> [*]: ссылка отправлена
```

### 5.1. `/start`
- **UPSERT** в таблицу `users` (`INSERT ... ON CONFLICT (telegram_id) DO UPDATE`): `telegram_id`, `first_name`, `last_name`, `username`, `language_code`, `created_at`, `last_active_at`.
- Если пользователь заблокирован (`is_banned = true`) — бот не отвечает.
- Если пользователь **уже купил** продукт — вместо описания: «Вы уже совершили покупку» и кнопка повторного получения ссылки.
- Поддержка deep-link: `/start ref_123` → `users.source = 'ref_123'` (отслеживание источника рекламы).
- Сообщение: фото продукта (опционально) + краткое описание + inline-кнопка **«🛒 Купить»**.

### 5.2. «Купить»
- Новое сообщение не отправляется — **редактируется текущее** (`edit_message_text` / `edit_message_caption`).
- Выводятся: номер карты (в `<code>`, копируется по нажатию), владелец, сумма, инструкция.
- Кнопки: **«⬅️ Назад»**.
- Состояние FSM: `BuyStates.waiting_receipt`.
- Если у пользователя уже есть платёж в статусе `pending` — «Ваш чек проверяется, пожалуйста, подождите», новый чек не принимается.
- Если продажи выключены в настройках (`sales_enabled = false`) — «Продажи временно приостановлены».

### 5.3. Отправка чека
- Принимается: `photo`, `document` (mime: `image/jpeg`, `image/png`, `image/webp`, `application/pdf`), размер ≤ 10 МБ.
- Текст, стикеры, голосовые и пр. → сообщение пользователя удаляется, сообщение бота редактируется: «Пожалуйста, отправьте чек в виде фото или файла».
- При успехе — см. раздел 7.

## 6. Механизм «чистого чата»

Цель: в чате пользователя **одновременно только 1 сообщение бота** (основной «экран»).

| Правило | Реализация |
|---|---|
| Бот хранит ID последнего сообщения для каждого пользователя | Redis: `ui:last_msg:{user_id}` → `message_id` (TTL 48 ч) |
| Нажатие кнопки | Не новое сообщение, а `edit_message_*` того же |
| Полная смена экрана (например, чек принят) | Старое `delete_message`, новое отправляется, ID сохраняется |
| Команда `/start` и неверные сообщения пользователя | Бот их удаляет |
| Фото чека | **Не удаляется** (остаётся у пользователя как доказательство) |
| Сообщения старше 48 часов | Telegram не даёт удалить → ошибка тихо перехватывается, отправляется новое |
| Ошибка `message is not modified` | Тихо игнорируется |

Логика собрана в одной функции: `ui.render(user_id, text, keyboard, media=None)` — сама решает: редактировать или удалить и отправить заново.

## 7. Приём чека и отправка админам

```mermaid
sequenceDiagram
    participant U as Пользователь
    participant B as Бот
    participant DB as PostgreSQL
    participant R as Redis
    participant A as Админы (N)
    U->>B: фото / файл
    B->>R: проверка rate-limit
    B->>DB: есть pending? повтор file_unique_id?
    B->>DB: INSERT payments (status=pending)
    B->>U: «✅ Принято, ссылка придёт в течение 1 часа»
    B-->>A: фоновая задача: каждому админу чек + [✅ Подтвердить] [❌ Отклонить]
    B->>DB: admin_messages (payment_id, admin_id, message_id)
```

**Подробно:**
1. **Проверка дубля** по `file_unique_id` — если это же изображение уже использовалось в другом платеже, админ получает пометку ⚠️ «Этот чек уже отправлялся в платеже #123».
2. Запись в `payments`: `user_id`, `amount` (текущая сумма из настроек — история не ломается при смене цены), `file_id`, `file_unique_id`, `file_type`, `status='pending'`, `created_at`.
3. Сообщение пользователю, состояние FSM очищается.
4. **Рассылка админам (fan-out)** — в фоне, параллельно с `asyncio.Semaphore(10)`, при `TelegramRetryAfter` — ожидание и повтор. Сообщение админу:
   ```
   🧾 Новый платёж #1024
   👤 Имя: Javohir Akramov
   🆔 ID: 123456789  ·  @username
   💰 Сумма: 50 000 сум
   🕒 04.11.2026 11:42
   [✅ Подтвердить] [❌ Отклонить]
   ```
   callback_data: `pay:ok:1024`, `pay:no:1024` (через фабрику `CallbackData` aiogram).
5. ID каждого отправленного админу сообщения пишется в `admin_messages` — чтобы потом обновить его у всех админов.
6. **Контроль SLA:** если платёж не рассмотрен за 50 минут, worker шлёт админам напоминание («⏰ 3 платежа ждут больше 50 минут»).

## 8. Подтверждение / отклонение

### 8.1. Защита от гонки (race condition)
Если несколько админов нажимают одновременно — срабатывает только **первый**:
```sql
UPDATE payments
SET status = 'approved', reviewed_by = :admin_id, reviewed_at = now()
WHERE id = :payment_id AND status = 'pending'
RETURNING user_id;
```
Если строка не вернулась → админу `answer_callback_query("Платёж уже рассмотрен", show_alert=True)`.

### 8.2. Подтверждение
1. Создаётся ссылка (зависит от настройки):
   - **Вариант A (рекомендуется):** **одноразовая ссылка-приглашение** в закрытый канал/группу — `create_chat_invite_link(chat_id, member_limit=1, expire_date=+24 ч, name="pay#1024")`. Пересланная другим — не сработает.
   - **Вариант B:** постоянная ссылка из настроек (Google Drive, сайт и т.д.).
2. Пользователю: «🎉 Оплата подтверждена! Ссылка на скачивание программы: …». Если пользователь заблокировал бота → `users.is_blocked_bot = true`, уведомление админу.
3. `users.has_purchased = true`.
4. **У всех админов** сообщение редактируется: кнопки убираются, добавляется «✅ Подтвердил: @admin_name, 11:50».

### 8.3. Отклонение
1. По нажатию ❌ появляются готовые причины:
   - «Неверная сумма» · «Чек нечитаем» · «Оплата не поступила» · «Поддельный чек» · «✍️ Другая причина (написать)» · «⬅️ Отмена»
2. После выбора — атомарный `UPDATE`, как в 8.1 (`status='rejected'`, `reject_reason`).
3. Пользователю: «❌ Оплата отклонена. Причина: …» + кнопка **«🔄 Отправить чек заново»**.
4. У всех админов сообщение обновляется: «❌ Отклонил: @admin_name — причина».
5. При выборе «Поддельный чек» — опционально предлагается кнопка «🚫 Заблокировать пользователя».

## 9. Админ-панель

Вход: команда `/admin` (только для админов; остальным бот не отвечает). Внизу **ReplyKeyboard**:

```
[ ⚙️ Настройки ] [ 👥 Пользователи ] [ 💰 Продажи ]
[ 📢 Рассылка ] [ 🏠 Выход ]
```
(«Рассылка» — рекомендуемая дополнительная функция.)

Меню внутри панели тоже работают по принципу **редактирования одного сообщения**.

### 9.1. ⚙️ Настройки
| Настройка | Описание | Валидация |
|---|---|---|
| 💳 Номер карты | 16 цифр | только цифры, 16 шт., проверка Луна |
| 👤 Владелец карты | Имя фамилия | 3–64 символа |
| 💰 Цена | в сумах | целое положительное |
| 📝 Текст продукта | описание в /start (HTML) | ≤ 1024 симв. (с фото), иначе ≤ 4096 |
| 🖼 Фото продукта | опционально | photo |
| 🔗 Тип ссылки | одноразовый invite / постоянная | |
| 📣 ID канала | для варианта A | проверка, что бот — админ канала |
| 🔗 Постоянная ссылка | для варианта B | формат URL |
| 👮 Админы | добавить (по ID) / удалить / список | только супер-админ |
| 🔌 Продажи вкл/выкл | | |

- Каждое изменение: показывается текущее значение → админ отправляет новое → «✅ Сохранить / ❌ Отмена».
- Настройки хранятся в таблице `settings`, кэшируются в Redis; при изменении кэш сбрасывается сразу.
- Каждое изменение пишется в `audit_log` (кто, когда, старое → новое).

### 9.2. 👥 Пользователи
- Статистика: всего · сегодня · 7 дней · 30 дней · купили · заблокировали бота · конверсия (%).
- 🔍 Поиск по ID или @username → карточка пользователя (данные, история платежей, кнопки: «🚫 Заблокировать / ✅ Разблокировать», «🔗 Отправить ссылку повторно», «✉️ Написать»).
- 📄 Список с пагинацией (по 10, ◀️ ▶️), новые сверху.
- 📥 Экспорт в Excel — все пользователи файлом `.xlsx` (генерируется в фоне).

### 9.3. 💰 Продажи
- Выручка и количество: сегодня · неделя · месяц · всего.
- По статусам: ⏳ ожидают · ✅ подтверждены · ❌ отклонены.
- ⏳ **Список ожидающих** — по нажатию снова открывается чек с кнопками подтверждения/отклонения (если админ потерял сообщение).
- По админам: кто сколько рассмотрел, среднее время рассмотрения.
- 📥 Экспорт в Excel (с диапазоном дат).

### 9.4. 📢 Рассылка — дополнительно
- Админ отправляет текст/фото → предпросмотр → «Всем / Только покупателям / Не купившим» → подтверждение.
- Через worker, **≤ 25 сообщений/с** (лимит Telegram — 30/с), с учётом `RetryAfter`.
- Итог: доставлено / заблокировали / ошибки.

## 10. База данных

Схема таблиц (SQL) — **идентична разделу 10 узбекской части** (`users`, `payments`, `admin_messages`, `admins`, `settings`, `audit_log`), включая индексы и частичный уникальный индекс `ux_payments_one_pending` (у пользователя может быть только один `pending`-платёж).

```mermaid
erDiagram
    users ||--o{ payments : "совершает"
    payments ||--o{ admin_messages : "рассылается"
    admins ||--o{ payments : "рассматривает"
    admins ||--o{ audit_log : "пишет"
```

**Ключи Redis:**

| Ключ | Назначение | TTL |
|---|---|---|
| `fsm:{bot}:{chat}:{user}:state/data` | FSM aiogram (RedisStorage) | 24 ч |
| `ui:last_msg:{user_id}` | ID последнего сообщения бота | 48 ч |
| `cache:settings` | все настройки (hash) | 10 мин + сброс при изменении |
| `cache:admins` | ID админов (set) | 10 мин + сброс при изменении |
| `rl:{user_id}` | счётчик rate-limit | 1–5 с |
| `seen:user:{id}` | обновлять `last_active_at` раз в 5 минут, а не на каждое сообщение | 5 мин |

## 11. Высокая нагрузка и скорость (500+ пользователей)

### 11.1. Целевые показатели
| Показатель | Требование |
|---|---|
| Одновременно активных пользователей | ≥ 500 (с запасом до 2 000) |
| Время работы хендлера (p95) | ≤ 150 мс |
| Время ответа пользователю (p95) | ≤ 1 с |
| Входящий поток апдейтов | ≥ 100 update/с стабильно |
| Ошибки | < 0,1 % |

### 11.2. Меры
1. **Webhook** — Telegram сам присылает апдейты, нет задержки polling. Защита `secret_token`.
2. **Полная асинхронность** — запрещены блокирующие вызовы (`requests`, `time.sleep`, синхронные драйверы БД). CPU-задачи (генерация Excel) — в `asyncio.to_thread`.
3. **Параллельная обработка апдейтов** — `handle_in_background=True` (webhook), медленный запрос не блокирует остальных.
4. **Пулы соединений** — Postgres: `pool_size=20, max_overflow=10, pool_pre_ping=True`; Redis: пул 50.
5. **Кэширование** — настройки и список админов не читаются из БД на каждый запрос (Redis + локальный in-memory кэш 30 с).
6. **Минимум записей** — `last_active_at` раз в 5 минут; в `/start` — один UPSERT-запрос.
7. **Фоновые задачи** — fan-out админам, рассылки, напоминания, экспорт не держат хендлер.
8. **Соблюдение лимитов Telegram** — глобально ~30 сообщений/с, в один чат ~1 сообщение/с. Middleware автоповтора при `TelegramRetryAfter`; рассылка через token-bucket 25/с.
9. **Rate-limit (антифлуд)** — более 2 действий в секунду от пользователя игнорируются; чеки — не более 3 в минуту.
10. **Индексы** — на все колонки фильтрации и сортировки (раздел 10).
11. **Горизонтальное масштабирование** — stateless, 2+ инстанса за Nginx.
12. **Нагрузочное тестирование** — перед сдачей через **Locust** или скрипт, отправляющий фейковые апдейты на webhook: сценарий 500 одновременных пользователей × 5 минут; результат сдаётся отчётом.

### 11.3. Требования к серверу (минимум)
| Ресурс | 500 польз. | 2 000+ польз. |
|---|---|---|
| CPU | 2 vCPU | 4 vCPU |
| RAM | 2 ГБ | 4 ГБ |
| Диск | 20 ГБ SSD | 40 ГБ SSD |
| ОС | Ubuntu 22.04/24.04 | |

## 12. Безопасность

1. **Токены и пароли** только в `.env`, не попадают в репозиторий (`.gitignore`).
2. **Проверка админа** через middleware: каждый хендлер и callback админ-роутера работает только для ID из `cache:admins`. В callback проверка повторяется (защита от подделки callback_data).
3. **Webhook** — проверка заголовка `X-Telegram-Bot-Api-Secret-Token`; Nginx принимает только с IP Telegram (149.154.160.0/20, 91.108.4.0/22).
4. **SQL-инъекции** — только ORM/параметризованные запросы.
5. **HTML-инъекции** — имя пользователя в сообщениях админам экранируется `html.escape`.
6. **Поддельные чеки** — проверка дубля `file_unique_id`; админ обязан проверить поступление денег в банковском приложении (бот этого автоматически не делает).
7. **Утечка ссылки** — одноразовый invite (`member_limit=1`, 24 ч).
8. **Резервные копии** — ежедневный `pg_dump`, хранение 14 дней, опционально отправка супер-админу файлом в Telegram.
9. **Аудит** — все действия админов в `audit_log`.

## 13. Обработка ошибок и логирование

| Ситуация | Действие |
|---|---|
| Пользователь заблокировал бота (`Forbidden`) | `is_blocked_bot=true`, не ошибка |
| `message is not modified` | тихо игнорировать |
| `message to delete not found` / старше 48 ч | тихо игнорировать |
| `RetryAfter` | подождать указанное время и повторить (макс. 3 раза) |
| Обрыв БД / Redis | переподключение, пользователю «Техническая неполадка, попробуйте чуть позже», событие в Sentry |
| Непредвиденная ошибка | глобальный error handler → лог + Sentry + краткое сообщение супер-админу (без спама: раз в 5 минут) |

Логи в JSON, уровень `INFO`, для каждого апдейта: `update_id`, `user_id`, имя хендлера, время обработки (мс). Ротация логов, хранение 7 дней.

## 14. Структура проекта

Структура папок, файлов и `.env.example` — **идентична разделу 14 узбекской части** (`app/handlers/user`, `app/handlers/admin`, `services`, `db/repositories`, `middlewares`, `worker`, `texts/uz.py` и `texts/ru.py`, `migrations`, `tests`, `loadtest`, `docker-compose.yml`, `nginx/bot.conf`).

## 15. Деплой

1. VPS (Ubuntu), домен и A-запись.
2. `docker compose up -d` — сервисы: `bot`, `worker`, `postgres`, `redis`, `nginx` (+ `certbot`).
3. `alembic upgrade head` — автоматически при старте контейнера.
4. При старте бота: `set_webhook(url, secret_token, allowed_updates=[...], drop_pending_updates=False)`.
5. `restart: unless-stopped` — после перезагрузки сервера бот поднимается сам.
6. Данные Postgres и Redis — в Docker volume.
7. Обновление: `git pull && docker compose up -d --build` — простой ≤ 10 с (Telegram подождёт и повторит отправку webhook).

## 16. Тексты бота

Интерфейс бота по умолчанию — **на узбекском** (целевая аудитория), тексты — в разделе 16 узбекской части. Архитектура поддерживает i18n (`texts/uz.py`, `texts/ru.py`): русский интерфейс можно включить позже выбором языка при `/start` без изменения логики. Тексты продукта, цена и реквизиты редактируются через «⚙️ Настройки».

## 17. Критерии приёмки

- [ ] После `/start` пользователь появляется в БД; повторный `/start` не создаёт дубль.
- [ ] На протяжении всей покупки в чате пользователя **не больше 1** сообщения бота (кроме фото чека).
- [ ] Чек доходит до **всех** админов за ≤ 5 с.
- [ ] Если 2 админа одновременно жмут «Подтвердить» — ссылка уходит **1 раз**, второму — «уже рассмотрено».
- [ ] После подтверждения/отклонения сообщение обновляется у всех админов.
- [ ] У пользователя не может быть 2 платежей `pending` одновременно.
- [ ] Изменения настроек видны новым пользователям сразу (≤ 1 с).
- [ ] Обычный пользователь не имеет доступа к `/admin` и админ-callback'ам.
- [ ] Нагрузочный тест: 500 одновременных пользователей × 5 минут, p95 ≤ 1 с, ошибок < 0,1 %.
- [ ] После перезагрузки сервера бот работает автоматически, данные и состояния FSM не теряются.
- [ ] Excel-экспорт корректно открывается.
- [ ] Код: README, `.env.example`, миграции, тесты основных сервисов (pytest, покрытие ≥ 60 %).

## 18. Этапы работ

| # | Этап | Результат | Ориент. срок |
|---|---|---|---|
| 1 | Каркас проекта, Docker, схема БД, миграции | Пустой бот запускается | 1 день |
| 2 | Сценарий пользователя: start, покупка, чек, чистый чат | Пользователь может отправить чек | 2 дня |
| 3 | Отправка админам, подтверждение/отклонение, ссылка | Полный цикл продажи | 2 дня |
| 4 | Админ-панель: настройки, пользователи, продажи, экспорт | Панель готова | 2–3 дня |
| 5 | Рассылка, напоминания, аудит, бэкапы | Доп. функции | 1–2 дня |
| 6 | Тесты, нагрузочный тест, оптимизация | Отчёт | 1–2 дня |
| 7 | Деплой, документация, сдача | Работающий бот | 1 день |
| | **Итого** | | **~10–13 рабочих дней** |
