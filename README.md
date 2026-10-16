# ИТ-элемент [29]

Корпоративная система учёта IT-оборудования. Версия 0.1.0, **этап 1: серверный каркас**.

Реализованы FastAPI, проверяемая конфигурация, PostgreSQL/SQLAlchemy, Alembic,
справочники подразделений, сотрудников и мест, health API, тесты и Docker Compose.
Frontend сейчас содержит только техническую страницу состояния с оригинальным логотипом.
Авторизации и бизнес-операций пока нет; это основа разработки, а не готовая v0.1.

## Быстрый запуск через Docker

Нужны Docker Engine/Desktop с Linux containers и Docker Compose v2+.
В корне репозитория скопируйте `.env.example` в `.env` и установите случайный
`POSTGRES_PASSWORD`. Пустой пароль останавливает Compose. `.env` не попадает в Git.
Пароли с `$` или `#` заключайте в одинарные кавычки в dotenv-файле.

```powershell
Copy-Item .env.example .env
# Отредактируйте POSTGRES_PASSWORD в .env перед следующей командой.
docker compose config --quiet
docker compose build
docker compose up -d --wait postgres
docker compose run --rm --no-deps backend python -m alembic upgrade head
docker compose up -d --wait
```

Откройте [техническую страницу](http://localhost:8080).
Проверки: [liveness](http://localhost:8080/api/v1/health/live),
[readiness](http://localhost:8080/api/v1/health/ready).
При успехе API возвращает `{"status":"ok"}`. Readiness при недоступной БД или
отставшей миграции возвращает HTTP 503 и `{"status":"not_ready"}`.
Неизвестные API-пути дают 404. OpenAPI выключена по умолчанию.

Миграции выполняются отдельной командой **до запуска** backend. Обычный `up` на пустой
БД не заменяет `alembic upgrade head`: backend останется not ready.
Для просмотра состояния: `docker compose ps`, логов: `docker compose logs --tail=100 backend`.
Остановка с сохранением БД и файлов: `docker compose down` (без `-v`).

## Backend без Docker

Нужны Python 3.12 и PostgreSQL 17. Создайте отдельную локальную БД и пользователя;
задайте их параметры в корневом `.env` (host/port относятся к нативной PostgreSQL).

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
Set-Location backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000
```

API: [http://127.0.0.1:8000/api/v1/health/ready](http://127.0.0.1:8000/api/v1/health/ready).
Для локальной OpenAPI явно задайте `ENABLE_API_DOCS=true` и откройте `/docs` на порту 8000.
Остановка Uvicorn: Ctrl+C. Конфигурация `.env` разрешается от расположения проекта,
а не от текущей рабочей папки. Переменные процесса имеют приоритет над `.env`.
Нативный запуск не поднимает frontend/proxy: для всего контура используйте Compose.

Зависимости закреплены в requirements.txt / requirements-dev.txt; диапазоны совместимости
описаны в pyproject.toml. При обновлении пересобирайте фиксацию версий и запускайте весь набор.

## Проверки

Из `backend`:

```powershell
..\.venv\Scripts\python.exe -m pytest -q
..\.venv\Scripts\python.exe -m ruff check .
..\.venv\Scripts\python.exe -m ruff format --check .
```

Обычный pytest явно пропускает PostgreSQL integration. Полный набор в отдельном
одноразовом контейнерном окружении (из корня):

```powershell
docker compose -f compose.test.yml up --build --abort-on-container-exit --exit-code-from tests
docker compose -f compose.test.yml down
```

Для нативной integration задайте **все** POSTGRES_* переменные процесса на отдельную
тестовую БД, затем `RUN_DB_TESTS=1` и `pytest -q`. Имя БД обязано оканчиваться на `_test`.
Этот набор выполняет downgrade схемы и допустим только на одноразовых данных.
Контейнерный набор не использует основные volumes и не публикует PostgreSQL порт.

## Документация

- [Архитектура и структура](ARCHITECTURE.md).
- [Текущая и целевая модель данных](DATABASE.md).
- [Этапы разработки](ROADMAP.md).
- [Фактически выполненные проверки и ограничения](PROGRESS.md).
- [Linux, HTTPS, резервирование и восстановление](docs/DEPLOYMENT.md).
- [Правила разработки](AGENTS.md).
- [План текущего этапа](docs/superpowers/plans/2026-10-16-stage-1.md).

Материалы CartridgeDesk не предоставлены. Реальные данные, GLPI.xlsx и интеграции
не импортировались. Никакие внешние хранилища корпоративных данных не используются.
