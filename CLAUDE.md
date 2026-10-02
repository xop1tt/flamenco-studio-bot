# Claude Code Instructions

## Project

This is the Flamenco Studio project.

The repository contains an existing Telegram bot and will be extended with a web application.

The detailed web development plan is located in:

```text
WEBSITE_PLAN.md
```

Always read `WEBSITE_PLAN.md` before working on the web application.

---

# 1. Core principle

The project must have one source of truth for business logic.

Telegram and Website are two interfaces to the same system.

Correct architecture:

```text
Telegram Bot ──────┐
                    ▼
              Shared Services
                    ▲
                    │
Web API ────────────┘
                    │
                    ▼
                PostgreSQL
```

Do NOT create:

```text
Telegram → separate business logic

Website → duplicated business logic
```

If business logic currently lives inside Telegram handlers, move it into reusable services when necessary.

Do not blindly refactor working code.

---

# 2. First rule: inspect before changing

Before modifying code:

1. Inspect the repository.
2. Understand the existing architecture.
3. Find the relevant implementation.
4. Find related database tables and migrations.
5. Find existing tests.
6. Understand side effects.
7. Only then make changes.

Never guess the implementation when the repository can answer the question.

Do not invent files, functions, classes, database tables or APIs that may already exist.

---

# 3. Do not start the entire website automatically

The project must be developed incrementally.

When asked to implement a feature:

1. Understand the request.
2. Inspect existing code.
3. Identify affected components.
4. Explain important architectural implications if necessary.
5. Implement only the requested stage.
6. Run relevant tests.
7. Review the diff.
8. Report what changed.

Do not silently continue to the next stage.

---

# 4. Existing Telegram bot

The Telegram bot is existing production/business functionality.

Do not break it.

Before changing shared logic:

- understand how the Telegram bot calls it;
- identify all callers;
- preserve existing behavior;
- run relevant tests;
- if tests do not exist, perform appropriate manual verification.

Do not rewrite the Telegram bot merely to make the web application easier to implement.

---

# 5. Business logic

Business logic should live in reusable services.

Examples:

```text
UserService
ScheduleService
BookingService
PaymentService
SupportService
```

These are examples, not mandatory names.

Use the naming and architecture that best fit the existing project.

Handlers should primarily:

- receive input;
- validate transport-level data;
- call services;
- format responses.

They should not contain large amounts of business logic if that logic needs to be reused by the web application.

---

# 6. Database

Use the existing PostgreSQL database.

Before creating a new table:

1. Search for an existing table representing the same concept.
2. Search migrations.
3. Search models/repositories.
4. Determine whether the existing schema can be reused.

Do not create duplicate tables for concepts that already exist.

Examples of things that should normally have one source of truth:

- users;
- classes;
- schedule;
- bookings;
- balances;
- packages;
- payments;
- support tickets.

---

# 7. Database migrations

All schema changes must use the project's migration system.

Do not make undocumented manual database changes.

Before creating a migration:

- inspect existing migration conventions;
- preserve foreign keys;
- preserve indexes;
- preserve constraints;
- consider existing data;
- consider rollback where appropriate.

After creating a migration, verify it against the existing schema.

---

# 8. Booking system

Booking is business-critical.

Never rely solely on frontend checks.

Bad:

```text
Frontend:
"3 places available"

Backend:
"insert booking"
```

Correct:

```text
Backend/database:
atomically verify availability
and create booking
```

Preserve existing transaction semantics.

Pay particular attention to:

- class capacity;
- concurrent requests;
- duplicate bookings;
- race conditions;
- database constraints;
- transaction isolation;
- cancellation behavior.

If the existing project already has a safe implementation, reuse it.

Do not replace a safe booking implementation with a simpler but unsafe one.

---

# 9. Payments

Payments are security-critical.

If the existing project uses YooKassa or another provider:

- inspect the existing implementation first;
- reuse the existing payment logic where possible;
- do not duplicate payment processing for the website.

Never trust the frontend to determine payment success.

Correct principle:

```text
Frontend
   ↓
Backend
   ↓
Payment provider
   ↓
Verified payment status
   ↓
Business operation
```

Preserve:

- idempotency;
- payment status verification;
- ledger logic;
- balance updates;
- duplicate callback protection;
- refund logic, if present.

Never log or expose:

- payment secrets;
- API credentials;
- bot tokens;
- database passwords.

---

# 10. Authentication

Authentication must be implemented securely.

If Telegram authentication is used:

- verify the authentication data on the backend;
- never trust client-provided identity data without verification;
- never expose bot tokens in frontend code;
- map the authenticated Telegram identity to the existing user model.

Do not create duplicate users when an existing user can be identified.

---

# 11. Authorization

Authentication and authorization are different.

Every admin endpoint must verify that the current user has the required privileges.

Never rely on:

```text
/admin
```

or a frontend route alone for security.

The backend must enforce authorization.

---

# 12. API

API endpoints must:

- validate input;
- authenticate requests where required;
- authorize privileged actions;
- return appropriate HTTP status codes;
- avoid leaking internal errors;
- avoid exposing secrets;
- use existing business services.

Do not put database/business logic directly into route handlers when it belongs in a reusable service.

---

# 13. Frontend

The frontend should consume the backend API.

Do not:

- connect directly to PostgreSQL;
- put database credentials in frontend code;
- duplicate business rules;
- hardcode dynamic schedule data;
- hardcode balances;
- trust frontend calculations for payments or booking.

The frontend is a presentation/client layer.

Backend is the source of truth.

---

# 14. Error handling

Handle errors intentionally.

Examples:

```text
401 Unauthorized
403 Forbidden
404 Not Found
409 Conflict
422 Validation Error
500 Internal Server Error
```

Do not expose stack traces or internal implementation details to end users.

For user-facing errors, return useful messages.

For developers, log enough information to diagnose the problem without exposing secrets.

---

# 15. Security

Always consider:

- authentication;
- authorization;
- input validation;
- SQL injection;
- XSS;
- CSRF where applicable;
- rate limiting;
- session security;
- secure cookies/tokens;
- payment security;
- Telegram authentication verification;
- admin access control.

Never commit:

```text
.env
.env.local
BOT_TOKEN
TELEGRAM_BOT_TOKEN
DATABASE_PASSWORD
DATABASE_URL with credentials
YOOKASSA_SECRET_KEY
API_KEY
PRIVATE_KEY
```

If a secret is discovered in tracked files, stop and report it rather than copying it elsewhere.

---

# 16. Environment variables

Use environment variables for secrets and environment-specific configuration.

Example:

```text
DATABASE_URL
BOT_TOKEN
YOOKASSA_SECRET_KEY
```

Do not put actual credentials into source code.

Do not put actual credentials into documentation.

Do not put actual credentials into `CLAUDE.md`.

---

# 17. Dependencies

Before adding a dependency:

1. Check whether the functionality already exists.
2. Check whether the project already has an equivalent dependency.
3. Prefer established, maintained packages.
4. Avoid adding a dependency for trivial functionality.
5. Explain significant new dependencies.

Do not add frameworks merely because they are popular.

---

# 18. Architecture decisions

When there are multiple reasonable solutions:

1. Prefer the simplest solution that fits the existing project.
2. Prefer reuse over rewriting.
3. Prefer one source of truth.
4. Prefer maintainability over cleverness.
5. Prefer fewer infrastructure components.
6. Prefer incremental changes.

Do not introduce:

- microservices;
- Kubernetes;
- event buses;
- unnecessary message queues;
- multiple databases;

unless there is a concrete requirement.

---

# 19. File organization

Follow the existing repository conventions when possible.

Do not reorganize the entire repository without a specific reason.

If a new frontend/backend structure is necessary, introduce it incrementally.

Before moving files:

- find imports;
- find references;
- check tests;
- check deployment;
- check scripts.

---

# 20. Testing

After meaningful changes, run the relevant tests.

At minimum, pay particular attention to:

### Users

- authentication;
- existing user lookup;
- duplicate users.

### Schedule

- available classes;
- closed classes;
- capacity.

### Booking

- successful booking;
- duplicate booking;
- full class;
- concurrent booking;
- cancellation.

### Payments

- successful payment;
- failed payment;
- duplicate payment;
- repeated callback;
- balance update.

### Authorization

- normal user;
- admin;
- unauthorized user;
- unauthenticated user.

### Existing bot

Ensure the modified shared functionality still works through Telegram.

---

# 21. Git

Before making changes:

```bash
git status
```

Review the current state.

Do not overwrite unrelated user changes.

Before finishing a task:

```bash
git diff
```

Review all modifications.

Do not commit unless explicitly requested.

Never commit secrets.

---

# 22. Working with user changes

The repository may contain uncommitted work.

If `git status` shows changes that you did not create:

- do not delete them;
- do not reset them;
- do not overwrite them;
- do not use destructive git commands.

If they conflict with the requested work, explain the conflict before proceeding.

---

# 23. Documentation

When introducing a significant architectural decision, document it.

Update documentation when necessary:

- README;
- API documentation;
- environment variable documentation;
- migration notes;
- architecture documentation.

Do not create documentation for every trivial code change.

---

# 24. Development stages

The expected development order is:

```text
Stage 0
Audit
    ↓
Stage 1
Shared business logic / refactoring
    ↓
Stage 2
Backend API
    ↓
Stage 3
Public website
    ↓
Stage 4
Authentication
    ↓
Stage 5
Client area
    ↓
Stage 6
Booking
    ↓
Stage 7
Payments
    ↓
Stage 8
Admin panel
    ↓
Stage 9
Testing
    ↓
Stage 10
Deployment
```

Do not implement all stages in one task.

---

# 25. Stage completion

When a stage is complete, report:

```text
Implemented:
- ...

Files changed:
- ...

Database changes:
- ...

Tests:
- ...

Manual checks:
- ...

Potential issues:
- ...

Next stage:
- ...
```

Do not automatically implement the next stage.

---

# 26. Before asking questions

Do not ask the user for information that can be determined by inspecting the repository.

Search the repository first.

Only ask the user when:

- the decision is genuinely product/business-related;
- multiple implementations have materially different consequences;
- required information does not exist in the repository;
- an action could destroy or significantly alter existing data;
- credentials or external service configuration are required.

---

# 27. Product decisions

Do not invent business rules.

Examples:

- how long before a class a booking can be cancelled;
- whether cancelled bookings restore balance;
- whether a user can book without available lessons;
- refund policy;
- expiration of packages;
- late cancellation rules;
- maximum number of simultaneous bookings.

If the existing project already defines a rule, preserve it.

If no rule exists and implementation requires one, ask the user before inventing it.

---

# 28. UI/UX

The website should be:

- responsive;
- mobile-friendly;
- simple;
- fast;
- accessible;
- visually coherent.

Do not spend excessive time on visual polish before core functionality works.

Priority:

```text
Correctness
    ↓
Security
    ↓
Usability
    ↓
Performance
    ↓
Visual polish
```

---

# 29. API and frontend contracts

When creating API endpoints, keep request/response schemas explicit.

Avoid returning arbitrary database objects directly.

Define appropriate schemas/DTOs.

Do not expose:

- passwords;
- tokens;
- internal credentials;
- unnecessary database fields;
- private admin data.

---

# 30. Performance

Do not optimize prematurely.

However:

- avoid N+1 database queries;
- add appropriate indexes when justified;
- paginate large lists;
- avoid fetching unnecessary data;
- avoid loading the entire schedule/user list when only a small page is needed.

Measure before introducing complicated caching.

---

# 31. Logging

Logs should help diagnose:

- failed authentication;
- failed booking;
- payment problems;
- unexpected exceptions;
- external service failures.

Never log:

- passwords;
- authentication secrets;
- payment secrets;
- bot tokens;
- full sensitive payment information.

---

# 32. External services

Before integrating or modifying:

- Telegram;
- YooKassa;
- hosting;
- email;
- other third-party APIs;

inspect the existing integration first.

Do not create a second integration when the project already has one that can be reused.

---

# 33. Important instruction about implementation

When the user asks:

> "Implement stage X"

Do exactly that stage.

Do not silently:

- redesign unrelated architecture;
- rewrite the bot;
- migrate unrelated database tables;
- add unrelated features;
- redesign the UI;
- deploy the application.

If you discover something that should be done later, document it under:

```text
Follow-up
```

and continue with the requested task if it is safe.

---

# 34. Important instruction about uncertainty

If you are uncertain about existing behavior:

DO NOT guess.

Search the repository.

If the answer still cannot be determined, explain the ambiguity and ask the user when the decision affects business behavior or data integrity.

---

# 35. Final project goal

The final architecture should provide:

```text
                    Flamenco Studio
                          │
             ┌────────────┴────────────┐
             │                         │
        Telegram Bot              Website
             │                         │
             └────────────┬────────────┘
                          │
                   Shared Services
                          │
                    PostgreSQL
                          │
                ┌─────────┴─────────┐
                │                   │
             YooKassa          Other services
```

The goal is not to build two applications.

The goal is to build one Flamenco Studio system with multiple interfaces.

Keep the architecture simple, secure, maintainable and inexpensive to operate.