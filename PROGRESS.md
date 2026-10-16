# Состояние проекта

Дата: 2026-10-16 (Asia/Yekaterinburg).

## Этап 1

**Архитектура и серверный каркас реализованы. Нативный backend с PostgreSQL проверен.
Контейнерная приёмка остаётся открыта: на компьютере отсутствует Docker Engine/WSL.**

Выполнено:

- Создан новый Git-репозиторий в исходно пустой папке D:\IT Element29.
- README, ARCHITECTURE, DATABASE, ROADMAP, AGENTS, план этапа и инструкция Linux/HTTPS/backup.
- Модульный FastAPI backend, Pydantic Settings, скрытый пароль, корректный URL подключения.
- SQLAlchemy 2, управление engine lifecycle и сессией запроса с явным commit.
- PostgreSQL 17, Alembic, обратимая начальная миграция departments/employees/locations.
- UUID, timezone-aware timestamps, FK RESTRICT, unique/check, индексы, архивирование.
- GET /api/v1/health/live и /ready; readiness проверяет подключение и актуальную ревизию.
- Нет публичных бизнес-операций; OpenAPI выключена по умолчанию, CORS не открыт.
- Dockerfiles и Compose: frontend, backend, PostgreSQL, Nginx; постоянные volumes;
  снаружи только proxy на loopback; отдельный запуск миграций до API.
- Техническая страница состояния с настоящими API-проверками и исходными логотипами.
- Отдельный disposable PostgreSQL-контур тестов; production volumes не используются.
- Версии Python-зависимостей зафиксированы; .env, данные и служебные инструменты исключены из Git.

## Выполненные проверки

| Проверка | Результат |
|---|---|
| pytest, Python 3.12.14 + PostgreSQL 17.11, RUN_DB_TESTS=1 | **14 passed**, без пропусков |
| Ruff check | Passed |
| Ruff format --check | 17 файлов отформатированы |
| Alembic upgrade → downgrade base → upgrade | Passed, настоящая PostgreSQL |
| Alembic check | Нет расхождений ORM и миграции |
| FK, unique, непустые значения, UTC, rollback запроса | Passed |
| Конфликт окружения миграций | Regression воспроизведён на прежнем коде и проходит после исправления |
| Alembic upgrade head --sql | SQL успешно сгенерирован |
| Настоящий Uvicorn HTTP через loopback | live=200 и ready=200 |
| pg_dump -Fc → pg_restore в новую отдельную БД | Совпадают вымышленная тестовая запись и ревизия 0001_directories |
| Docker Compose v5.6.0 config --quiet | Оба Compose-файла валидны |
| Nginx 1.30.6 -t | Proxy и frontend конфигурации валидны |
| Оригинальные логотипы | Скопированы без преобразований |
| Независимое code review | Два существенных замечания исправлены, см. docs/REVIEW-STAGE-1.md |

API-тесты в ограниченном sandbox зависали на сетевых примитивах TestClient; итоговый
набор выполнен с разрешением локальных сокетов. Ошибки первоначальных прогонов не
выдаются за успешные проверки. Подготовленный переносимый PostgreSQL использовался
только на 127.0.0.1:55432, с уникальным случайным паролем, без Windows-службы.
Временные серверы после проверки остановлены. `.venv` и `.scratch` остаются локально
и не входят в репозиторий; штатный запуск описан в README.

## Что ещё не проверено

- Docker image build, `compose up`, контейнерные healthchecks, restart/persistence volumes.
- Контейнерный backup/restore файлов и PostgreSQL; нативный PostgreSQL restore проверен.
- Корпоративный HTTPS (нужны согласованные DNS/сертификаты PKI).
- Браузерные E2E: рабочий React UI появится на этапе 2; техническая страница пока без E2E.

Для закрытия контейнерной приёмки на машине с Docker: команды README, затем
`docker compose -f compose.test.yml up --build --abort-on-container-exit --exit-code-from tests`,
рестарт основного контура и restore drill из docs/DEPLOYMENT.md. Не считать `config --quiet`
эквивалентом контейнерного запуска.

## Границы результата

Этапы **2–8 не выполнялись**. Авторизация, роли, React UI, складские операции, карточки,
перемещения, обслуживание, аудит, статистика, XLSX, загрузка файлов и demo seed ещё
не реализованы. Полная модель этих модулей описана как целевая, а не как существующая схема.
Материалы CartridgeDesk отсутствовали; старый проект не изменялся. Реальные данные
и GLPI.xlsx не импортировались. Следующий этап — авторизация, RBAC и дизайн-система.
