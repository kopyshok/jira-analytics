# JiraAnalysis — Инструкция для системного администратора

Этот документ содержит всё необходимое для установки, обновления и обслуживания сервиса на корпоративном сервере.
Разработчик не имеет SSH-доступа к серверу — все операции выполняет сисадмин по этой инструкции.

---

## 1. Предварительные требования

### 1.1 Сервер
- Минимум: 4 vCPU / 16 GB RAM / 100 GB SSD
- ОС: Ubuntu 22.04 LTS (или другой дистрибутив с Docker 24+)
- Доступ в интернет с сервера (для pull образов из GHCR, синхронизации с Jira, LLM API)

### 1.2 Установка Docker
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# Перелогиниться чтобы группа применилась
newgrp docker
```

### 1.3 Проверка
```bash
docker --version          # должно быть 24+
docker compose version    # должно быть 2.x
```

---

## 2. Первоначальная установка

### 2.1 Создать структуру каталогов
```bash
sudo mkdir -p /opt/jira-analytics/prod/proxy/certs
sudo mkdir -p /opt/jira-analytics/staging
sudo chown -R $USER:$USER /opt/jira-analytics
```

### 2.2 Скопировать файлы из репозитория
Разработчик передаёт (или кладёт в репозиторий) следующие файлы:
```
deploy/prod/docker-compose.yml    → /opt/jira-analytics/prod/docker-compose.yml
deploy/prod/.env.example          → /opt/jira-analytics/prod/.env.example
deploy/prod/proxy/nginx.conf      → /opt/jira-analytics/prod/proxy/nginx.conf
deploy/staging/docker-compose.yml → /opt/jira-analytics/staging/docker-compose.yml
deploy/staging/.env.example       → /opt/jira-analytics/staging/.env.example
```

### 2.3 Настроить TLS-сертификат для prod

Положить сертификат (выданный корпоративным CA) в:
```
/opt/jira-analytics/prod/proxy/certs/fullchain.pem   — сертификат + промежуточные
/opt/jira-analytics/prod/proxy/certs/privkey.pem     — приватный ключ
```
```bash
chmod 600 /opt/jira-analytics/prod/proxy/certs/privkey.pem
```

Обновить hostname в nginx.conf:
```bash
nano /opt/jira-analytics/prod/proxy/nginx.conf
# Заменить: server_name jira-analytics.company.local;
# На реальный внутренний домен
```

### 2.4 Создать .env для prod
```bash
cd /opt/jira-analytics/prod
cp .env.example .env
nano .env
chmod 600 .env
```

Заполнить все поля (пустые строки = обязательно):

| Переменная | Как получить |
|---|---|
| `DB_PASSWORD` | `python3 -c "import secrets; print(secrets.token_hex(24))"` |
| `JWT_SECRET_KEY` | `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `APP_VERSION` | Спросить у разработчика (например `v1.0.0`) |
| `CORS_ORIGINS` | URL сервиса, например `https://jira-analytics.company.local` |
| `ADMIN_EMAIL` | Email первого администратора |
| `ADMIN_PASSWORD` | Временный пароль (сменить после первого входа) |
| `GEMINI_API_KEY` | Ключ Gemini (разработчик предоставит) |
| `OPENROUTER_API_KEY` | Ключ OpenRouter (разработчик предоставит) |

**Сохранить DB_PASSWORD и JWT_SECRET_KEY в надёжном месте (менеджер паролей).**
Если они будут утеряны, потребуется пересоздание БД и разлогин всех пользователей.

### 2.5 Авторизоваться в GHCR (GitHub Container Registry)
```bash
# Токен предоставит разработчик (scope: read:packages)
echo "<GITHUB_TOKEN>" | docker login ghcr.io -u <github_username> --password-stdin
```

### 2.6 Подтянуть образ
```bash
cd /opt/jira-analytics/prod
docker compose pull
```

### 2.7 Применить миграции базы данных
```bash
docker compose run --rm backend alembic upgrade head
```

### 2.8 Создать первого администратора
```bash
docker compose run --rm backend python scripts/create_admin.py
```

### 2.9 Запустить prod
```bash
docker compose up -d
```

### 2.10 Проверить
```bash
docker compose ps           # все сервисы должны быть healthy
docker compose logs backend --tail=50
curl -k https://localhost/health/ready   # должен вернуть {"status":"ok"}
```
Открыть в браузере: `https://jira-analytics.company.local`
Войти с ADMIN_EMAIL / ADMIN_PASSWORD, сменить пароль, настроить Jira-credentials в разделе «Настройки».

### 2.11 Убрать временный пароль
```bash
nano /opt/jira-analytics/prod/.env
# Удалить строку ADMIN_PASSWORD=...
docker compose up -d backend   # перезапустить только backend
```

---

## 3. Установка staging (опционально)

### 3.1 Создать .env для staging
```bash
cd /opt/jira-analytics/staging
cp .env.example .env
nano .env
chmod 600 .env
```
Использовать **другие** значения DB_PASSWORD и JWT_SECRET_KEY (не prod!).
`AUTH_COOKIE_SECURE=false` уже выставлен в примере — staging работает по HTTP.

### 3.2 Запустить staging
```bash
cd /opt/jira-analytics/staging
docker compose pull
docker compose run --rm backend alembic upgrade head
docker compose run --rm backend python scripts/create_admin.py
docker compose up -d
```

Staging доступен по `http://<server-ip>:8080`.

---

## 4. Обновление до новой версии

> Перед каждым обновлением сделать снимок ВМ.

```bash
cd /opt/jira-analytics/staging

# 1. Обновить тег версии в .env
nano .env   # APP_VERSION=v1.2.3

# 2. Подтянуть новый образ в staging
docker compose pull

# 3. Применить миграции в staging
docker compose run --rm backend alembic upgrade head

# 4. Запустить staging и проверить вручную в браузере
docker compose up -d
# Открыть http://<server>:8080, проверить вход, дашборд, один сценарий

# 5. Если staging OK — переключить prod
cd /opt/jira-analytics/prod
nano .env   # APP_VERSION=v1.2.3
docker compose pull
docker compose run --rm backend alembic upgrade head
docker compose up -d

# 6. Финальная проверка prod
curl -k https://localhost/health/ready
```

---

## 5. Откат к предыдущей версии

```bash
cd /opt/jira-analytics/prod
nano .env   # Вернуть APP_VERSION на предыдущий тег, например v1.1.0
docker compose up -d
# Миграции не откатывать — схема forward-compatible
```

Если откат образа не помогает (данные повреждены):
1. Остановить prod: `docker compose down`
2. Восстановить снимок ВМ (сделанный до обновления)
3. Сообщить разработчику

---

## 6. Ежедневное обслуживание

### Посмотреть логи
```bash
cd /opt/jira-analytics/prod
docker compose logs backend --tail=100 -f     # потоком
docker compose logs postgres --tail=50
docker compose logs proxy --tail=50
```

### Статус контейнеров
```bash
docker compose ps
```

### Зайти в базу данных (psql)
```bash
docker compose exec postgres psql -U app -d jira_analytics_prod
```

### Перезапустить отдельный сервис
```bash
docker compose restart backend    # не пересоздаёт контейнер
docker compose up -d backend      # пересоздаёт (применяет изменения в .env)
```

---

## 7. Обновление TLS-сертификата

```bash
# Заменить файлы сертификата:
cp new_fullchain.pem /opt/jira-analytics/prod/proxy/certs/fullchain.pem
cp new_privkey.pem   /opt/jira-analytics/prod/proxy/certs/privkey.pem
chmod 600 /opt/jira-analytics/prod/proxy/certs/privkey.pem

# Перезагрузить nginx без даунтайма:
docker compose exec proxy nginx -s reload
```

---

## 8. Обновление staging данными из prod (еженедельно)

```bash
cd /opt/jira-analytics/prod

# Дамп prod БД
docker compose exec postgres pg_dump -U app jira_analytics_prod > /tmp/prod_dump.sql

# Восстановить в staging
cd /opt/jira-analytics/staging
docker compose exec -T postgres psql -U app -c "DROP DATABASE IF EXISTS jira_analytics_staging;"
docker compose exec -T postgres psql -U app -c "CREATE DATABASE jira_analytics_staging;"
docker compose exec -T postgres psql -U app jira_analytics_staging < /tmp/prod_dump.sql

docker compose restart backend
rm /tmp/prod_dump.sql
```

---

## 9. Мониторинг

Рекомендуется: UptimeRobot (бесплатный тариф) или корпоративный инструмент мониторинга.
Эндпоинт для проверки: `https://jira-analytics.company.local/health`
Ожидаемый ответ: `{"status":"ok"}` с HTTP 200.

---

## 10. Частые проблемы

| Симптом | Причина | Решение |
|---|---|---|
| `backend` не становится healthy | БД ещё стартует | Подождать 60-90 сек, `docker compose logs backend` |
| 502 Bad Gateway | backend упал | `docker compose logs backend --tail=50`, `docker compose restart backend` |
| SSL certificate error в браузере | Сертификат не доверенный / истёк | Обновить сертификат (§7) |
| `alembic upgrade head` падает с ошибкой | Конфликт миграций | Отправить вывод разработчику |
| Контейнер падает с OOM | Нехватка памяти | Проверить `docker stats`, увеличить лимиты в `deploy.resources.limits` |
| `docker compose pull` возвращает 401 | GHCR токен истёк | Повторить `docker login ghcr.io` (§2.5) |

---

## 11. Контакты

По вопросам, не покрытым этой инструкцией, обращаться к разработчику с:
- Полным выводом `docker compose logs <service> --tail=100`
- Выводом `docker compose ps`
- Описанием шагов, которые привели к проблеме
