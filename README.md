# Jira Analytics & Planning Service

Сервис для анализа Jira и квартального планирования трудозатрат.

## 🎯 Назначение

- Интеграция с Jira Cloud: загрузка проектов, задач, worklogs
- Нормализация и мэппинг: привязка к управленческим категориям
- Аналитика факта: трудозатраты по людям, проектам, категориям
- Планирование квартала: расчёт capacity по производственному календарю
- Отчётность: PDF, Excel, PowerPoint

## 🏗 Архитектура

```
SQLite MVP → PostgreSQL (future)
```

| Слой | Технология |
|------|-----------|
| Backend | Python + FastAPI |
| Database | SQLite (MVP) → PostgreSQL |
| ORM | SQLAlchemy |
| Migrations | Alembic |
| Frontend | React + TypeScript |

## 🚀 Быстрый старт

```bash
# Создать виртуальное окружение
python -m venv venv
source venv/bin/activate  # Linux/Mac
# или: venv\Scripts\activate  # Windows

# Установить зависимости
pip install -r requirements.txt

# Скопировать конфиг
cp .env.example .env
# Отредактировать .env с вашими Jira credentials

# Создать миграции
alembic upgrade head

# Запустить сервер
uvicorn app.main:app --reload
```

API доступен: http://localhost:8000
Документация: http://localhost:8000/docs

## 📁 Структура проекта

```
jira-analytics/
├── app/
│   ├── api/           # FastAPI роуты
│   ├── models/        # SQLAlchemy модели
│   ├── repositories/  # Слой доступа к данным
│   ├── services/      # Бизнес-логика
│   ├── connectors/    # Интеграция с Jira
│   ├── config.py      # Конфигурация
│   ├── database.py    # Настройка БД
│   └── main.py        # Точка входа
├── alembic/           # Миграции БД
├── requirements.txt
└── .env.example
```

## 📊 Roadmap

- [x] M1: Технический каркас
- [ ] M2: Загрузка Jira
- [ ] M3: Аналитика факта
- [ ] M4: Planning
- [ ] M5: Экспорты

## 📄 Лицензия

MIT
