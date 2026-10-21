# ИТ-элемент [29]

Корпоративная система учёта IT-оборудования. Этапы 1–2 включают серверный каркас,
авторизацию, четыре роли и React-интерфейс на русском языке. Текущий этап 3:
каталог расходников, совместимость, фотографии, складские документы, личные
черновики, остатки, история и Excel. Фактический статус приёмки — в PROGRESS.md.
Реестр оборудования и этапы 4–8 в этот выпуск не входят.

## Локальный запуск через Docker

Нужны Docker Desktop/Engine с Linux containers и Docker Compose >=2.24.
Для нового окружения скопируйте `.env.example` в `.env`. Задайте два разных случайных
пароля длиной не менее 24 символов: `POSTGRES_PASSWORD` владельца БД и
`APP_DB_PASSWORD` ограниченной роли `APP_DB_USER`. `.env` не входит в Git.
Значения с `$` или `#` заключайте в одинарные кавычки. Существующий `.env` не перезаписывайте.

```powershell
Copy-Item .env.example .env # Только при первой настройке
# Задайте пароли в .env, затем:
docker compose config --quiet
docker compose build
docker compose up -d --wait postgres
docker compose run --rm --no-deps migrate
docker compose run --rm --no-deps migrate python -m app.cli provision-db-role
docker compose up -d --wait
# Только если в БД ещё нет пользователей; пароль вводится скрыто:
docker compose exec backend python -m app.cli create-admin --username admin --display-name "Администратор"
```

Интерфейс: **[http://localhost:8080](http://localhost:8080)**. Войдите с выбранными
при настройке логином и паролем. Стандартного пароля и публичной регистрации нет.
Повторный `create-admin` при существующих пользователях откажет, не изменяя данные.
Если продолжаете прежний локальный стенд, используйте существующую учётную запись.

Миграции выполняет отдельный процесс `migrate`, API сам схему не меняет.
После новой миграции повторите `provision-db-role`, чтобы обновить разрешения runtime-роли.
Dev Compose сохраняет совместимость со старым `.env` без APP_DB_* (backend тогда работает
от владельца); для ограничения прав добавьте APP_DB_* и выполните provisioning.
Для предприятия используйте отдельную конфигурацию из [DEPLOYMENT.md](DEPLOYMENT.md).
Корневой Compose всегда предназначен для локального HTTP, а не корпоративного HTTPS.

Проверки: [live](http://localhost:8080/api/v1/health/live) и
[ready](http://localhost:8080/api/v1/health/ready). Readiness возвращает 200 только
при доступной БД и актуальной ревизии Alembic; иначе 503 без SQL и секретов.
OpenAPI по умолчанию выключена. БД и backend не публикуют порты на хосте.

```powershell
docker compose ps
docker compose logs --tail=100 backend
docker compose down # Без -v: БД и файлы сохраняются
```

Обновление существующего локального стенда выполняйте вручную из корня проекта.
Сборка не останавливает приложение; резервная копия создаётся после остановки
записывающих сервисов. После **каждой** команды проверяйте успешное завершение;
при ошибке backup или миграции не переходите к следующему шагу.

```powershell
docker compose build backend migrate frontend
docker compose stop backend proxy
.\.venv\Scripts\python.exe scripts/backup_local.py --output "backups/local-$(Get-Date -Format yyyyMMdd-HHmmss)"
# Продолжать только после сообщения «Проверены dump, архив файлов и SHA256»:
docker compose run --rm --no-deps migrate
docker compose run --rm --no-deps migrate python -m app.cli provision-db-role
docker compose up -d --wait
Invoke-RestMethod http://localhost:8080/api/v1/health/ready
```

Скрипту нужен Python 3.12+ (можно заменить путь к `.venv` на установленный `python`).
Он проверяет PostgreSQL dump и архив фотографий; незавершённый backup не считается
подтверждённым. Существующий `.env` и volumes сохраняйте. Если миграция завершилась
ошибкой, не восстанавливайте копию поверх текущей БД: разберите ошибку и используйте
план восстановления в отдельный пустой контур из DEPLOYMENT.md.
Перенос проверенных выпусков на Linux: [RELEASE.md](RELEASE.md).

## Backend и frontend без Docker

Нужны Python 3.12+, PostgreSQL 17 и Node.js 24 с pnpm 10.28.2.
Создайте локальную БД; задайте POSTGRES_* в `.env` для подключения владельца к ней.
Не используйте корпоративные данные в разработке.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt
Set-Location backend
..\.venv\Scripts\python.exe -m alembic upgrade head
..\.venv\Scripts\python.exe -m app.cli provision-db-role
..\.venv\Scripts\python.exe -m app.cli create-admin --username admin --display-name "Администратор"
```

После provisioning измените POSTGRES_USER/POSTGRES_PASSWORD в локальном `.env` на
APP_DB_USER/APP_DB_PASSWORD для запуска API. Владелец нужен только для миграций и
provisioning; его параметры храните отдельно. Запустите backend в первом терминале:

```powershell
Set-Location backend
..\.venv\Scripts\python.exe -m uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --no-proxy-headers --no-access-log
```

Во втором терминале из корня:

```powershell
corepack enable
Set-Location frontend
pnpm install --frozen-lockfile
pnpm dev
```

Откройте **[http://127.0.0.1:5173](http://127.0.0.1:5173)**. Vite перенаправляет `/api`
на `127.0.0.1:8000`; разрешённые APP_ORIGINS уже перечислены в `.env.example`.
Если меняете порт, добавьте точный origin без завершающего `/`. Не запускайте одновременно
нативный backend и Docker на одной базе с разными версиями схемы.

## Проверки

Полный backend-набор с одноразовой PostgreSQL (не использует основные volumes):

```powershell
docker compose -f compose.test.yml -p e29-stage3-tests run --rm --build tests
.\.venv\Scripts\python.exe -m ruff check backend
.\.venv\Scripts\python.exe -m ruff format --check backend
.\.venv\Scripts\python.exe -m pytest scripts/tests -q
Set-Location frontend
pnpm test
pnpm build
pnpm format:check
```

Нативный `pytest` из backend пропускает PostgreSQL integration, если не задать
`RUN_DB_TESTS=1`, `TEST_CLUSTER_MARKER` и все `TEST_POSTGRES_*`. Compose выше поднимает
отдельный кластер с контрольным marker. Каждый тест создаёт новую БД и применяет
только forward-миграции. DROP/TRUNCATE/downgrade не используются. Действующий стенд,
его `.env`, базы и volumes не меняются. Пропуски не означают успех.

Браузерные сценарии находятся в `frontend/e2e`. Запускайте только на отдельном тестовом
стенде: они создают вымышленных пользователей, меняют их роли, пароли и блокировки.
Задайте `E2E_BASE_URL`, `E2E_ADMIN_USERNAME`, `E2E_ADMIN_PASSWORD` через защищённое
окружение процесса. Пароль не записывайте в историю терминала или Git.
Затем из frontend: `pnpm exec playwright install chromium` и `pnpm test:e2e`.
Трассировки выключены; screenshots/test-results игнорируются Git.

## Документация

- [Архитектура](ARCHITECTURE.md), [схема данных](DATABASE.md), [этапы](ROADMAP.md).
- [Фактические проверки и ограничения](PROGRESS.md).
- [Контракт авторизации, права и интерфейс](docs/STAGE-2-DESIGN.md).
- [Контракт склада](docs/STAGE-3-DESIGN.md), [план завершения этапа 3](docs/STAGE-3-COMPLETION.md).
- [Сборка автономного выпуска](RELEASE.md), [Ubuntu, HTTPS, backup и restore](DEPLOYMENT.md).
- [Правила проекта](AGENTS.md).

Оригинальные логотипы сохранены. В интерфейсе используются отдельные PNG с прозрачным
фоном, полученные локальной обработкой исходников по согласованию с пользователем.
CartridgeDesk не изменяется, реальные данные и GLPI.xlsx не импортируются.
