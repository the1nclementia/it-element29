# Развёртывание и восстановление

## Статус этапа 1

Это технический контур без авторизации. Не вводить реальные корпоративные данные до
этапа 2 и проверки прав. Публично доступны только проверки состояния; CRUD API отсутствует.
Compose использует bootstrap-owner PostgreSQL: разделение migration/runtime roles и
ограничения audit_logs входят в этап 2. Веб-приложение работает без root.

## Linux-сервер

1. Установить Docker Engine и Compose plugin из официального репозитория для вашей ОС.
2. Скопировать/клонировать репозиторий в каталог приложения. Секреты передать отдельно.
3. `cp .env.example .env`; задать уникальный пароль; `chmod 600 .env`.
4. `docker compose config --quiet` (обычный `config` может вывести секреты — не публикуйте его).
5. `docker compose build`.
6. `docker compose up -d --wait postgres`.
7. `docker compose run --rm --no-deps backend python -m alembic upgrade head`.
8. `docker compose up -d --wait`.
9. `curl --fail http://127.0.0.1:8080/api/v1/health/ready` и проверить техническую страницу.

Только proxy публикует loopback-порт. PostgreSQL и files используют постоянные named volumes.
Сеть backend/БД internal: контейнеры приложений не имеют внешнего исходящего маршрута.
Образы Python 3.12 slim, PostgreSQL 17.11 alpine, Nginx 1.30.6 alpine. Перед корпоративным
выпуском зафиксировать проверенные image digests в принятом реестре и настроить обновления.
Нельзя менять major PostgreSQL заменой image tag над существующим volume.

## HTTPS предприятия

На хосте корпоративный Nginx принимает 443 и передаёт запросы на loopback:8080.
Шаблон: `infra/nginx/corporate-tls.conf.example`. Согласовать DNS, имя сертификата,
цепочку и доверие с владельцами корпоративной PKI; ключ хранить вне Git с ограничением прав.
Проверить `nginx -t`, затем загрузить конфигурацию стандартным механизмом администратора.
Проверить доверие цепочки в корпоративном браузере. Самоподписанный сертификат
не генерируется и не подставляется автоматически.

Текущий API не доверяет forwarded headers (Uvicorn `--no-proxy-headers`). На этапе 2
до внедрения защищённых cookies и редиректов настроить передачу исходного HTTPS через
два proxy и разрешить доверие только известным адресам proxy, проверить CSRF и Secure.

## Обновление

Сначала резервная копия. Затем `docker compose build`, `docker compose stop backend`,
`docker compose run --rm --no-deps backend python -m alembic upgrade head`,
`docker compose up -d --wait`, проверка readiness. При неудачной миграции не запускать
новую версию до разбора; изменения PostgreSQL DDL транзакционны. Nginx повторно разрешает
имена контейнеров через Docker DNS (127.0.0.11), поэтому смена IP не требует ручного reload.

`alembic downgrade base` удаляет справочники и **не является процедурой отката production**.
Откат версии проводить по совместимости миграций, либо восстановить согласованный backup
в отдельный контур и переключить трафик после проверки.

## Резервная копия PostgreSQL и файлов

Команды ниже предназначены для Bash на Linux, из корня репозитория.
На этапе 1 нет загрузок; процедура уже включает будущий files volume.
На время согласованного снимка остановить backend, чтобы БД и файлы соответствовали
друг другу. При ошибке выполнить `docker compose start backend` после диагностики.

```bash
set -e
umask 077
backup_dir="$(pwd)/backups/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup_dir"
docker compose stop backend
docker compose exec -T postgres sh -c 'pg_dump -Fc -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f /tmp/element29.dump'
docker compose cp postgres:/tmp/element29.dump "$backup_dir/database.dump"
docker compose run --rm --no-deps --user 0 -v "$backup_dir:/backup" backend python -c 'import tarfile; t=tarfile.open("/backup/files.tar.gz", "w:gz"); t.add("/app/uploads", arcname="files"); t.close()'
git rev-parse HEAD > "$backup_dir/revision.txt"
docker compose start backend
sha256sum "$backup_dir/database.dump" "$backup_dir/files.tar.gz" > "$backup_dir/SHA256SUMS"
```

Не переносите PostgreSQL binary dump через текстовое перенаправление старого PowerShell:
используйте `docker compose cp`. Backup содержит будущие персональные данные; хранить
зашифрованным по политике предприятия, отдельно от сервера, с доступом только операторов.
Рекомендуемый начальный регламент: ежедневные снимки, 7 ежедневных + 4 еженедельных,
ежемесячная проверка восстановления. RPO/RTO и хранение должен согласовать владелец сервиса.
Не включать приватные TLS-ключи или `.env` в общедоступный backup.

## Обязательная проверка восстановления

Используйте отдельный Compose project **element29-restore**, новую пустую БД и отдельные
volumes. Не восстанавливайте поверх работающей production. Скопируйте `.env` в
`.env.restore`, поменяйте POSTGRES_DB на element29_restore_test, HTTP_PORT на 8081,
оставьте HTTP_BIND=127.0.0.1. Установите права 600. Используйте ту же ревизию кода,
которая записана в revision.txt, и совместимую major PostgreSQL.

```bash
docker compose -p element29-restore --env-file .env.restore up -d --wait postgres
docker compose -p element29-restore --env-file .env.restore cp "$backup_dir/database.dump" postgres:/tmp/restore.dump
docker compose -p element29-restore --env-file .env.restore exec -T postgres sh -c 'pg_restore --exit-on-error --no-owner --no-privileges -U "$POSTGRES_USER" -d "$POSTGRES_DB" /tmp/restore.dump'
docker compose -p element29-restore --env-file .env.restore run --rm --no-deps --user 0 -v "$backup_dir:/backup:ro" backend python -c 'import os,tarfile; t=tarfile.open("/backup/files.tar.gz"); t.extractall("/tmp/restore-files", filter="data"); t.close(); import shutil; shutil.copytree("/tmp/restore-files/files", "/app/uploads", dirs_exist_ok=True); [os.chown(p,10001,10001) for d,ds,fs in os.walk("/app/uploads") for p in [d]+[os.path.join(d,n) for n in fs]]'
docker compose -p element29-restore --env-file .env.restore up -d --wait
curl --fail http://127.0.0.1:8081/api/v1/health/ready
```

Далее сравнить количество строк справочников и контрольную тестовую запись, проверить
версии Alembic, размеры/хеши файлов и их читаемость приложением. Записать время восстановления,
результат и исполнителя. После приёмки остановить только `element29-restore`.
Удалять его volumes можно лишь после проверки имени проекта и ненужности данных.

Контейнерная процедура backup/restore пока не прогонялась в этом окружении (нет Docker
Engine). Нативная проверка PostgreSQL и её точный результат фиксируются в PROGRESS.md.
