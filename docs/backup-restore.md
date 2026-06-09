# Резервное копирование БД и восстановление

Отдельный контейнер делает автоматические дампы Postgres с ротацией. Этот документ — инструкция для сисадмина: как подключить, настроить и восстановиться.

## Что это

Сервис `postgres-backup` на базе образа [`prodrigestivill/postgres-backup-local`](https://github.com/prodrigestivill/docker-postgres-backup-local). Внутри: cron + `pg_dump` + автоматическое удаление старых файлов. Дампы складываются в `/backups` внутри контейнера, наружу прокидываются через volume.

Структура каталога `/backups`:

```
/backups/
├── daily/     — последние N ежедневных дампов
├── weekly/    — последние N еженедельных
├── monthly/   — последние N ежемесячных
└── last/      — симлинки на самые свежие файлы каждой категории
```

Имя файла: `<DB>-<YYYYMMDD>-<HHMMSS>.sql.gz` (gzip-сжатый SQL-дамп).

## Добавление в docker-compose.yml

Вставить рядом с сервисом `postgres`:

```yaml
postgres-backup:
  image: prodrigestivill/postgres-backup-local:16
  restart: unless-stopped
  depends_on:
    postgres:
      condition: service_healthy
  environment:
    POSTGRES_HOST: postgres
    POSTGRES_DB: jira_analytics_prod
    POSTGRES_USER: app
    POSTGRES_PASSWORD: ${DB_PASSWORD}
    SCHEDULE: ${BACKUP_SCHEDULE:-@daily}
    BACKUP_KEEP_DAYS: ${BACKUP_KEEP_DAYS:-7}
    BACKUP_KEEP_WEEKS: ${BACKUP_KEEP_WEEKS:-4}
    BACKUP_KEEP_MONTHS: ${BACKUP_KEEP_MONTHS:-6}
    BACKUP_DIR: /backups
    TZ: Europe/Moscow
  volumes:
    - ./backups:/backups
  networks:
    - internal
  logging:
    driver: json-file
    options:
      max-size: "10m"
      max-file: "3"
```

Версия тэга образа (`:16`) должна совпадать с мажорной версией Postgres — иначе `pg_dump` несовместим.

## Переменные окружения

| Переменная | Назначение | Дефолт | Примеры |
|---|---|---|---|
| `POSTGRES_HOST` | Имя сервиса БД в compose-сети | — | `postgres` |
| `POSTGRES_DB` | Имя базы | — | `jira_analytics_prod` |
| `POSTGRES_USER` | Пользователь БД | — | `app` |
| `POSTGRES_PASSWORD` | Пароль (из `.env`) | — | `${DB_PASSWORD}` |
| `SCHEDULE` | Расписание (cron-формат или alias) | `@daily` | `0 3 * * *` (03:00), `0 */6 * * *` (каждые 6ч), `@weekly` |
| `BACKUP_KEEP_DAYS` | Сколько ежедневных копий хранить | `7` | `14` |
| `BACKUP_KEEP_WEEKS` | Сколько еженедельных хранить | `4` | `8` |
| `BACKUP_KEEP_MONTHS` | Сколько ежемесячных хранить | `6` | `12` |
| `BACKUP_DIR` | Путь внутри контейнера | `/backups` | — |
| `TZ` | Часовой пояс (для расписания) | `UTC` | `Europe/Moscow` |

Расписание в формате cron — 5 полей: `минуты часы день месяц день_недели`. Aliases: `@daily` (00:00), `@hourly`, `@weekly` (вс 00:00), `@monthly` (1-е 00:00).

## Дополнения в .env

Добавить в production `.env` (всё опционально, дефолты подходят):

```bash
# --- Backup schedule and retention ---
BACKUP_SCHEDULE=0 3 * * *      # каждый день в 03:00
BACKUP_KEEP_DAYS=7
BACKUP_KEEP_WEEKS=4
BACKUP_KEEP_MONTHS=6
```

## Проверка после первого запуска

```bash
# Контейнер поднят и здоровый
docker compose ps postgres-backup

# Логи — должно быть "Backup running" по расписанию
docker compose logs postgres-backup --tail=50

# Ручной триггер бэкапа (не ждать расписания)
docker compose exec postgres-backup /backup.sh

# Проверить что файл создался
ls -lh ./backups/daily/

# Проверить целостность дампа (не разворачивая)
gunzip -t ./backups/last/<DB>-latest.sql.gz && echo OK
```

## Восстановление из бэкапа

> ВНИМАНИЕ: восстановление перезапишет текущую базу. Перед операцией остановить backend, чтобы избежать конфликтов.

```bash
# 1. Остановить приложение (БД оставить запущенной)
docker compose stop backend

# 2. Выбрать файл — самый свежий в last/ или конкретную дату из daily/
ls -lt ./backups/daily/ | head

# 3. Развернуть дамп
BACKUP_FILE=./backups/daily/jira_analytics_prod-20260609-030000.sql.gz

# Вариант A: пересоздать базу с нуля (чище)
docker compose exec postgres dropdb -U app jira_analytics_prod
docker compose exec postgres createdb -U app jira_analytics_prod
gunzip -c "$BACKUP_FILE" | docker compose exec -T postgres psql -U app -d jira_analytics_prod

# Вариант B: накатить поверх существующей (только если знаешь что делаешь)
gunzip -c "$BACKUP_FILE" | docker compose exec -T postgres psql -U app -d jira_analytics_prod

# 4. Поднять backend
docker compose start backend

# 5. Проверить /health/ready
curl -fsS http://localhost/health/ready
```

## Хранение и безопасность

- Каталог `./backups` на хосте — права `chmod 700`, владелец root (или dedicated user). Дампы содержат всю БД, включая хеши паролей пользователей.
- Если на хосте мало места — смонтировать `./backups` на отдельный диск/раздел или сетевую шару (NFS/SMB).
- Регулярно (раз в квартал) проверять восстанавливаемость: развернуть свежий бэкап на staging-БД и убедиться что приложение поднимается.
- Off-site копия: настроить отдельную задачу (rsync/rclone) которая копирует `./backups/weekly/` и `./backups/monthly/` на удалённое хранилище. В `postgres-backup` это не входит — он только локально.

## Размер дампа и время

Ориентир (после миграции на Postgres 16, ~115k issues, ~6000 ворклогов в день):
- gzip-сжатый дамп: ~50–200 МБ
- время бэкапа: 10–60 секунд
- нагрузка на БД во время дампа: умеренная, но при `@hourly` лучше выносить на slave/replica (за рамками этого документа)

## Откат сервиса бэкапов

Если контейнер бэкапов мешает или ломается:

```bash
docker compose stop postgres-backup
docker compose rm -f postgres-backup
```

Существующие файлы в `./backups/` остаются нетронутыми.
