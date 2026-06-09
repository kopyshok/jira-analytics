# Карта прода для сисадмина

Где что лежит, как обновить, где смотреть логи и бэкапы. Документ — оглавление, детали — по ссылкам.

## Состав сервиса

Сервис собран из четырёх частей. На bare-metal развёртывании (вариант сисадмина компании) три из них работают как systemd-сервисы, четвёртая — статика, отдаваемая nginx.

| Часть | Что делает | Где живёт | Чем управляется |
|---|---|---|---|
| `backend` | FastAPI + APScheduler + sync-pipeline | `/opt/jira-analytics/app/` (исходники из git) | systemd unit `jira-analytics.service` |
| `frontend` | SPA (React, статика) | `/var/www/jira-analytics/` (содержимое `frontend/dist/`) | nginx раздаёт как статику |
| `postgres` | БД (PostgreSQL 16) | bare-metal Postgres, база `jira_analytics_prod` | systemd unit `postgresql.service` |
| `proxy` (nginx) | HTTPS + проксирование `/api/*` и `/events/*` в backend | nginx config | systemd unit `nginx.service` |

Если поднимать через docker compose — конфиг и порядок описаны в [`deploy/prod/docker-compose.yml`](../deploy/prod/docker-compose.yml) и [`deploy/prod/.env.example`](../deploy/prod/.env.example).

## Где что лежит на хосте (bare-metal)

```
/opt/jira-analytics/                  # клон git-репозитория
├── app/                              # backend код
├── frontend/dist/                    # собранная статика (после npm run build)
├── alembic/                          # миграции БД
├── data/                             # рабочие файлы backend (модели embeddings, кэш)
├── scripts/release.py                # релизный скрипт
└── .env                              # production конфиг (chmod 600, root)

/var/www/jira-analytics/              # симлинк или копия frontend/dist
/var/log/jira-analytics/              # логи backend (если настроен файловый sink)
/var/backups/postgres/                # дампы БД (см. ниже)
/etc/systemd/system/jira-analytics.service
/etc/nginx/sites-available/jira-analytics.conf
```

PostgreSQL — стандартный путь дистрибутива (`/var/lib/postgresql/16/main` на Debian/Ubuntu).

## Где `.env` и какие переменные

Боевой `.env` лежит в `/opt/jira-analytics/.env`. В git он не коммитится; шаблон — [`deploy/prod/.env.example`](../deploy/prod/.env.example).

Ключевые блоки:

- `DATABASE_URL=postgresql://app:<PASSWORD>@localhost:5432/jira_analytics_prod` — подключение к БД
- `JWT_SECRET=...` — секрет токенов; смена выкидывает всех пользователей
- `CORS_ORIGINS=https://...` — допустимые origin для фронта
- `DEBUG=false` — в проде только `false`
- `JIRA_*` — креды Jira как fallback, если в `app_setting` ещё ничего не записано (после первого входа админ задаёт их через UI)
- `BACKUP_*` — параметры бэкапа (см. ниже)

После правки `.env` — `systemctl restart jira-analytics`.

## Версии и обновление до новой версии

Текущая версия видна в шапке UI и в `app/config.py` → `app_version`.

Обновление до тега `vX.Y.Z`:

```bash
cd /opt/jira-analytics
sudo -u app git fetch --tags
sudo -u app git checkout vX.Y.Z

# Миграции БД (всегда перед рестартом backend)
sudo -u app /opt/jira-analytics/.venv/bin/alembic upgrade head

# Пересобрать фронт (если node на хосте — иначе собрать на CI и положить дистрибутив)
cd frontend
sudo -u app npm ci
sudo -u app npm run build

# Рестарт
sudo systemctl restart jira-analytics
sudo systemctl reload nginx
```

Откат: `git checkout vX.Y.(Z-1)` + `alembic downgrade -1` (если в релизе были миграции) + рестарт. Перед откатом — всегда свежий бэкап (см. ниже), миграции downgrade не всегда обратимы.

## Бэкапы БД

Полная инструкция — [`backup-restore.md`](./backup-restore.md). Здесь — только адреса:

- **Что бэкапится:** база `jira_analytics_prod` целиком (`pg_dump`-ом, gzip)
- **Где лежат файлы:** `/var/backups/postgres/` (или `./backups/` для docker-compose варианта)
  - `daily/` — последние 7 ежедневных
  - `weekly/` — последние 4 еженедельных
  - `monthly/` — последние 6 ежемесячных
  - `last/` — симлинки на самые свежие
- **Расписание:** ежедневно в 03:00 по умолчанию (`BACKUP_SCHEDULE=0 3 * * *`)
- **Когда чистится:** автоматически по `BACKUP_KEEP_DAYS/WEEKS/MONTHS`
- **Размер дампа:** ~50–200 МБ gzip, время — 10–60 секунд
- **Off-site копия:** **не настроена автоматически** — нужно отдельной задачей (rsync/rclone) гнать `weekly/` и `monthly/` на удалённое хранилище
- **Восстановление:** см. [`backup-restore.md`](./backup-restore.md), раздел «Восстановление из бэкапа»

Проверка работоспособности бэкапа — раз в квартал развернуть свежий дамп на staging-БД.

## Логи

| Источник | Где смотреть |
|---|---|
| backend (stdout/stderr) | `journalctl -u jira-analytics -f` |
| backend (sync pipeline + APScheduler) | туда же в journalctl |
| nginx access + error | `/var/log/nginx/access.log`, `/var/log/nginx/error.log` |
| postgres | `journalctl -u postgresql -f` или `/var/log/postgresql/` |

В docker-compose варианте всё через `docker compose logs <service> -f`.

## Healthchecks

- `GET /health/ready` — readiness (БД доступна, embeddings прогреты)
- `GET /health/live` — liveness (процесс жив)
- nginx должен дёргать `/health/ready` за `proxy_pass` и не отдавать клиенту, если 503

## Полезные команды

```bash
# Статус всех частей
systemctl status jira-analytics postgresql nginx

# Рестарт только backend
sudo systemctl restart jira-analytics

# Проверка миграций (что накатано / что не накатано)
sudo -u app /opt/jira-analytics/.venv/bin/alembic current
sudo -u app /opt/jira-analytics/.venv/bin/alembic history --verbose

# Подключиться к БД
sudo -u postgres psql jira_analytics_prod

# Размер БД
sudo -u postgres psql -c "SELECT pg_size_pretty(pg_database_size('jira_analytics_prod'));"

# Свежий бэкап вручную (не ждать расписания)
sudo -u postgres pg_dump -Fc jira_analytics_prod | gzip > /var/backups/postgres/manual/$(date +%F-%H%M).dump.gz
```

## Связанные документы

- [`backup-restore.md`](./backup-restore.md) — детально по бэкапам и восстановлению
- [`deploy/prod/docker-compose.yml`](../deploy/prod/docker-compose.yml) — конфиг docker-compose варианта
- [`deploy/prod/.env.example`](../deploy/prod/.env.example) — шаблон production `.env`
