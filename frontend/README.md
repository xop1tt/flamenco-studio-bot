# Flamenco Studio — публичный сайт

Next.js (App Router) + TypeScript + Tailwind CSS. Второй интерфейс к тому же
backend API, что описан в корневом `README.md` — сайт не хранит бизнес-данные
и не дублирует бизнес-логику бота, только отображает то, что отдаёт
`src/flamenco_bot/api` (см. корневой `WEBSITE_PLAN.md`).

Реализовано: публичные страницы без авторизации (Stage 3 — главная,
расписание, направления, абонементы, контакты), вход через Telegram
(Stage 4 — `/login`, сессия в httponly-cookie), личный кабинет (Stage 5 —
`/account`: профиль, баланс, мои занятия, поддержка), запись на занятия
прямо из расписания (Stage 6 — кнопка «Записаться»/«Войти и записаться» на
`/schedule`) и оплата абонементов (Stage 7 — кнопка «Купить» на
`/packages`, история и проверка статуса на `/account/payments`). ЮKassa к
сайту пока не подключена: `WEB_YOOKASSA_RETURN_URL` на backend пуст, поэтому
checkout отвечает 503 — весь остальной код уже готов, см. раздел ниже.

## Запуск

```bash
npm install
cp .env.example .env.local   # укажите API_BASE_URL и NEXT_PUBLIC_TELEGRAM_BOT_USERNAME
npm run dev
```

На `npm run dev` (`localhost`) виджет **всегда** покажет «Bot domain
invalid» — это не баг, а намеренное ограничение Telegram: виджет работает
только на настоящем публичном HTTPS-домене, привязанном к боту через
@BotFather (`/setdomain`). Подтверждено на практике, не только по
документации. Проверять живой вход имеет смысл только на реальном домене
после деплоя (Stage 6+) либо через временный HTTPS-туннель (ngrok/cloudflared)
с доменом, временно привязанным через `/setdomain`. До тех пор серверная
часть входа (`/api/auth/telegram`, cookie, `/account`) проверяется напрямую
HTTP-запросами с подписанным payload — см. коммиты Stage 4/5.

Откройте http://localhost:3000. По умолчанию сайт обращается к backend API
на `http://127.0.0.1:8000` — поднимите его отдельно:

```bash
# из корня репозитория, в виртуальном окружении backend
python -m flamenco_bot.api
```

## Переменные окружения

| Переменная | Обязательно | Назначение |
|---|:---:|---|
| `API_BASE_URL` | Нет (по умолчанию `http://127.0.0.1:8000`) | Базовый URL backend API. Запросы идут с сервера Next.js (серверные компоненты), а не из браузера — переменная намеренно без префикса `NEXT_PUBLIC_`, чтобы не попасть в клиентский бандл. |
| `NEXT_PUBLIC_TELEGRAM_BOT_USERNAME` | Для `/login` | Публичный `@username` бота для Telegram Login Widget (не секрет). Инлайнится в клиентский бандл на этапе `next build` — в Docker это build arg, а не runtime-переменная (см. корневой `compose.yaml`). |

## Данные и кэширование

Страницы `/`, `/schedule`, `/packages`, `/login` и весь `/account/*` показывают
живые данные (свободные места, цены абонементов, статус сессии, профиль) и
помечены `export const dynamic = "force-dynamic"`, чтобы Next.js не заморозил
их в статический HTML на этапе `next build`. Хедер сайта (`SiteHeader`) на
каждой странице читает cookie сессии — из-за этого **весь сайт** рендерится
динамически, даже `/directions` и `/contact`: это осознанный компромисс
(корректность состояния авторизации важнее статической оптимизации двух
страниц с текстом).

## Структура

```text
src/
├── app/
│   ├── login/      # Telegram Login Widget, редирект на / если уже вошёл
│   └── account/     # личный кабинет (Stage 5), требует сессию
│       ├── layout.tsx    # guard: редирект на /login без сессии
│       ├── page.tsx       # профиль + баланс (GET /api/users/me/profile)
│       ├── bookings/      # мои занятия, предстоящие/прошедшие
│       ├── payments/      # история платежей + «Проверить оплату»
│       │                  # (GET /api/payments/me, GET /api/payments/:id/check)
│       └── support/       # обращения: форма + список (GET/POST /api/support)
├── components/
│   ├── TelegramLoginWidget.tsx   # клиентский компонент — грузит виджет,
│   │                             # шлёт POST /api/auth/telegram
│   ├── AccountNav.tsx            # суб-навигация внутри /account
│   ├── BookableScheduleList.tsx  # расписание с кнопкой «Записаться» —
│   │                              # используется на /schedule (не на главной)
│   └── PackagesGrid.tsx          # каталог абонементов; кнопка «Купить»
│                                  # только когда передан isAuthenticated
│                                  # (на /packages; тизер на главной — без неё)
└── lib/
    ├── api.ts        # клиент к backend API (GET /api/schedule, /api/packages)
    ├── auth.ts       # getCurrentUser() — читает cookie сессии, спрашивает
    │                 # backend GET /api/auth/me (серверные компоненты)
    ├── account.ts    # getProfile/getMyBookings/getMySupportTickets/
    │                 # getMyPayments — то же, что auth.ts, но для
    │                 # /api/users, /api/bookings, /api/support, /api/payments
    ├── actions.ts    # Server Actions: logoutAction, submitSupportMessageAction,
    │                 # bookClassAction, startCheckoutAction, checkPaymentAction —
    │                 # все переиспользуют сообщения об ошибках backend'а
    │                 # вместо своего перевода
    ├── directions.ts # маркетинговые описания направлений (labels совпадают
    │                 # с CLASS_LABELS в src/flamenco_bot/class_catalog.py)
    └── format.ts      # форматирование дат/времени
```

Запросы из браузера к `/api/*` (например, `TelegramLoginWidget` →
`POST /api/auth/telegram`) идут на тот же origin сайта и проксируются к
backend через `rewrites()` в `next.config.ts` — отдельного CORS или
публичного порта у `api` для этого не нужно.

## Оплата (ЮKassa) — подготовлено, но не подключено

Весь путь готов и покрыт тестами (`tests/unit/test_api_payments.py`), но
намеренно не принимает реальные платежи: на backend пуст
`WEB_YOOKASSA_RETURN_URL` (см. корневой `env.example`), поэтому
`POST /api/payments/checkout` отвечает `503 "ЮKassa не настроена"` — та же
кнопка «Купить» и та же страница `/account/payments` уже работают с этим
статусом (показывают понятную ошибку, не падают).

Что сделано:
- `/packages` — кнопка «Купить» (авторизован) / «Войти и купить» (нет сессии)
  на каждом пакете, `startCheckoutAction` → `POST /api/payments/checkout`.
- При успехе — редирект на `confirmation_url` ЮKassa (внешний URL).
- `/account/payments` — история платежей + кнопка «Проверить оплату» для
  незавершённых (`checkPaymentAction` → `GET /api/payments/:id/check`), тот
  же принцип, что и в боте: никакого webhook, статус сверяется вручную по
  кнопке.

Что нужно сделать, чтобы включить реальные платежи:
1. Указать `YOOKASSA_SHOP_ID` и `YOOKASSA_SECRET_KEY` в `.env` (если ещё не
   указаны для бота — используется один и тот же магазин).
2. Указать `WEB_YOOKASSA_RETURN_URL` — адрес сайта, куда ЮKassa вернёт
   пользователя после оплаты, например
   `https://your-domain.example/account/payments`.
3. Перезапустить `api` (или весь `docker compose up -d --build`).

Фронтенд менять не нужно — он уже полностью готов к этому переключению.

## Известные ограничения (Follow-up)

- На странице «Контакты» — плейсхолдеры (адрес/телефон/соцсети/ссылка на
  бота в репозитории не найдены). Замените на реальные данные в
  `src/app/contact/page.tsx` перед запуском в продакшен.
- Вход только через Telegram; `/api/auth/register` и `/api/auth/login`
  (email/пароль) на backend есть, но на сайте для них пока нет формы —
  добавить, если продукту нужен вход без Telegram.
- Отмена записи — нет ни UI, ни backend-эндпоинта (в боте такого тоже нет,
  правило не определено — см. `WEBSITE_PLAN.md`, раздел 14: "не придумывать
  новые правила самостоятельно"). Привязка/отвязка Telegram из кабинета —
  тоже нет UI, хотя у `/api/auth/me/telegram` есть backend.

## Прочее

Это служебные файлы Next.js, не трогайте без необходимости:
`AGENTS.md`, `CLAUDE.md` (переадресует на `AGENTS.md`) — автоматически
создаются/обновляются самим `next dev`/`create-next-app` и описывают
особенности именно этой версии Next.js, отдельно от корневого `CLAUDE.md`
проекта.
