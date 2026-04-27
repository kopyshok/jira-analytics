# Auth + Мульти-пользователь — Дизайн (Вариант А)

**Дата:** 2026-04-27  
**Статус:** Approved  
**Подход:** Вариант А — фронтенд-защита (JWT без серверного middleware)

---

## Контекст

Сервис переходит от single-user (нет auth) к multi-user для ~6 руководителей одной компании.  
Вариант Б (серверный middleware + RBAC) зафиксирован как следующий шаг после Варианта А.

---

## Ограничения и решения

| Вопрос | Решение |
|---|---|
| Кол-во пользователей | ~6 менеджеров + 1 супер-менеджер + 1 admin |
| Auth | Email + пароль, Admin заводит вручную |
| Jira-токен | Глобальный, один на всех, меняет только Admin |
| Изоляция данных | Нет жёсткой изоляции — общие данные, фильтр по команде |
| Видимость чужих команд | Разрешена (можно вручную переключить фильтр) |
| База данных | SQLite остаётся |
| Деплой | Вне скоупа, отдельный этап |
| Самостоятельная регистрация | Нет — только Admin создаёт пользователей |
| Серверная защита endpoint'ов | Нет в Варианте А — только фронт скрывает UI |

---

## Модель данных

### Таблица `users`

| Поле | Тип | Ограничения |
|---|---|---|
| id | String(36) | PK, UUID |
| email | String(255) | unique, indexed, not null |
| password_hash | String(255) | bcrypt, not null |
| display_name | String(255) | not null |
| role | Enum | `admin` / `super_manager` / `manager`, not null |
| default_team | String(255) | nullable — null у super_manager и admin |
| is_active | Boolean | default True |
| created_at | DateTime | auto |
| updated_at | DateTime | auto |

### Роли

- **admin** — создаёт/редактирует пользователей, меняет Jira-токен, видит все команды, не фильтруется по команде
- **super_manager** — видит несколько команд одновременно (default_team = null, выбирает через существующий фильтр)
- **manager** — default_team заполнен, при входе фильтр автоматически выставляется на свою команду; может вручную переключиться

---

## Backend

### Новые endpoint'ы (`/api/v1/auth/`)

| Метод | Путь | Описание |
|---|---|---|
| POST | `/auth/login` | email + password → access token (JWT) |
| POST | `/auth/logout` | клиент удаляет токен (stateless — сервер ничего не хранит) |
| GET | `/auth/me` | возвращает текущего пользователя (id, email, display_name, role, default_team) |

### Новые endpoint'ы (`/api/v1/admin/users/`)

| Метод | Путь | Описание |
|---|---|---|
| GET | `/admin/users/` | список всех пользователей |
| POST | `/admin/users/` | создать пользователя |
| PUT | `/admin/users/{id}` | изменить (имя, роль, команда, активность) |
| POST | `/admin/users/{id}/reset-password` | сбросить пароль |

Admin-endpoint'ы в Варианте А не защищены серверным middleware (защита через фронт).  
В Варианте Б добавится `Depends(require_admin)`.

### JWT

- Библиотека: `python-jose` (уже в экосистеме FastAPI)
- Access token: срок 8 часов (рабочий день)
- Payload: `{ sub: user_id, role, default_team }`
- Refresh token: **нет** в Варианте А (упрощение)
- SECRET_KEY в `.env` → `Settings`

### Пароли

- bcrypt через `passlib`
- Минимальная длина: 8 символов
- Хранится только хэш

### Первоначальный Admin

Seed-скрипт `scripts/create_admin.py` — создаёт первого admin при пустой таблице users.  
Принимает email + пароль из аргументов CLI или `.env` (`ADMIN_EMAIL`, `ADMIN_PASSWORD`).

---

## Frontend

### Роутинг

- Все маршруты `/app/*` требуют наличия JWT в localStorage
- Если токен отсутствует → редирект на `/login`
- Проверка при старте приложения (до рендера Layout)

### Логин-страница (`/login`)

- Поля: email, пароль
- При успехе: токен сохраняется в `localStorage`, редирект на `/app/`
- При ошибке: сообщение «Неверный email или пароль»

### Текущий пользователь

- `GET /auth/me` при старте — загрузить профиль
- React Context `AuthContext` — хранит `{ user, token, logout }`
- `logout()` — удаляет токен из localStorage + редирект на `/login`

### Автоматический team-фильтр при входе

- Если `user.role === 'manager'` и `user.default_team` заполнен → выставить глобальный team-фильтр в `default_team`
- Если `admin` или `super_manager` — фильтр не выставляется (пользователь выбирает сам)
- Фильтр хранится в существующем стейте (FactFilterProvider или аналог)

### Admin-панель (`/app/settings/users`)

- Новая вкладка в `/settings` — «Пользователи» (видна только role=admin)
- Таблица пользователей: имя, email, роль, команда, активен
- Кнопки: создать, редактировать, сбросить пароль, деактивировать
- Форма создания: email, display_name, роль, команда (выпадающий список существующих команд из `/teams`), пароль

### Header

- Справа: имя текущего пользователя + кнопка «Выйти»
- Заменяет текущий placeholder (если есть) или добавляется в существующий Header

---

## Миграция

Alembic миграция `036_users.py`:
- Создаёт таблицу `users`
- Добавляет `ADMIN_EMAIL` / `ADMIN_PASSWORD` в `.env.example`

---

## Что остаётся открытым (Вариант Б)

- Серверный middleware `Depends(get_current_user)` на все endpoint'ы
- `Depends(require_admin)` на admin-endpoint'ы и смену Jira-токена
- Refresh tokens
- Rate limiting на `/auth/login`

---

## Зависимости

Новые пакеты в `requirements.txt`:
- `python-jose[cryptography]` — JWT
- `passlib[bcrypt]` — хэширование паролей
