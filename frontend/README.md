# Flamenco Studio — публичный сайт

Next.js (App Router) + TypeScript + Tailwind CSS. Второй интерфейс к тому же
backend API, что описан в корневом `README.md` — сайт не хранит бизнес-данные
и не дублирует бизнес-логику бота, только отображает то, что отдаёт
`src/flamenco_bot/api` (см. корневой `WEBSITE_PLAN.md`).

Реализовано: публичные страницы без авторизации (Stage 3 — главная,
расписание, направления, абонементы, контакты) и вход через Telegram
(Stage 4 — `/login`, сессия в httponly-cookie). Личный кабинет и запись на
занятия — следующие этапы.

## Запуск

```bash
npm install
cp .env.example .env.local   # укажите API_BASE_URL и NEXT_PUBLIC_TELEGRAM_BOT_USERNAME
npm run dev
```

Чтобы `/login` реально показал кнопку входа, в @BotFather должен быть указан
домен сайта для бота (команда `/setdomain`) — Telegram Login Widget
проверяет домен, с которого его загрузили, и без привязки покажет «Bot
domain invalid». На `localhost` виджет обычно не работает даже с привязкой;
проверяйте вход на реальном домене.

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

Страницы `/`, `/schedule`, `/packages` и `/login` показывают живые данные
(свободные места, цены абонементов, статус сессии) и помечены
`export const dynamic = "force-dynamic"`, чтобы Next.js не заморозил их в
статический HTML на этапе `next build`. Хедер сайта (`SiteHeader`) на каждой
странице читает cookie сессии — из-за этого **весь сайт** рендерится
динамически, даже `/directions` и `/contact`: это осознанный компромисс
(корректность состояния авторизации важнее статической оптимизации двух
страниц с текстом).

## Структура

```text
src/
├── app/
│   └── login/      # Telegram Login Widget, редирект на / если уже вошёл
├── components/
│   └── TelegramLoginWidget.tsx  # клиентский компонент — грузит виджет,
│                                 # шлёт POST /api/auth/telegram
└── lib/
    ├── api.ts        # клиент к backend API (GET /api/schedule, /api/packages)
    ├── auth.ts       # getCurrentUser() — читает cookie сессии, спрашивает
    │                 # backend GET /api/auth/me (серверные компоненты)
    ├── actions.ts    # Server Action logoutAction (форма "Выйти" в хедере)
    ├── directions.ts # маркетинговые описания направлений (labels совпадают
    │                 # с CLASS_LABELS в src/flamenco_bot/class_catalog.py)
    └── format.ts      # форматирование дат/времени
```

Запросы из браузера к `/api/*` (например, `TelegramLoginWidget` →
`POST /api/auth/telegram`) идут на тот же origin сайта и проксируются к
backend через `rewrites()` в `next.config.ts` — отдельного CORS или
публичного порта у `api` для этого не нужно.

## Известные ограничения (Follow-up)

- На странице «Контакты» — плейсхолдеры (адрес/телефон/соцсети/ссылка на
  бота в репозитории не найдены). Замените на реальные данные в
  `src/app/contact/page.tsx` перед запуском в продакшен.
- Вход только через Telegram; `/api/auth/register` и `/api/auth/login`
  (email/пароль) на backend есть, но на сайте для них пока нет формы —
  добавить, если продукту нужен вход без Telegram.
- Личный кабинет (профиль, баланс, мои занятия, история) и запись на
  занятия — Stage 5/6 по `WEBSITE_PLAN.md`, не входят в этот этап.

## Прочее

Это служебные файлы Next.js, не трогайте без необходимости:
`AGENTS.md`, `CLAUDE.md` (переадресует на `AGENTS.md`) — автоматически
создаются/обновляются самим `next dev`/`create-next-app` и описывают
особенности именно этой версии Next.js, отдельно от корневого `CLAUDE.md`
проекта.
