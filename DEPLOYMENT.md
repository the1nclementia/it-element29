# Развёртывание на Ubuntu 24.04

Используется отдельный `deploy/compose.yaml`; корневой `docker-compose.yml` предназначен для разработки. Серверные контуры `staging` и `production` имеют разные Compose projects, внешние volumes, state, секреты, DNS и сертификаты. Внутри staging также действуют production security settings. Этап 3 не включён.

## 1. Подготовить сервер и сеть

1. Выделите Ubuntu 24.04 с постоянным диском, синхронизацией времени и местом для текущих/предыдущих образов, PostgreSQL, файлов и как минимум двух резервных копий. Используйте отдельную служебную учётную запись с SSH-ключом и sudo; доступ к Docker socket эквивалентен root.
2. Установите Python 3.12+, curl, openssl, CA certificates, Docker Engine и Compose plugin >=2.24.0. Для сервера с разрешённым корпоративным репозиторием: `sudo apt-get update` и `sudo apt-get install python3 curl openssl ca-certificates`, Docker — по [официальной инструкции Ubuntu](https://docs.docker.com/engine/install/ubuntu/). Для полностью отключённого сервера заранее подготовьте подписанные пакеты именно Ubuntu 24.04 и нужной архитектуры: `containerd.io`, `docker-ce`, `docker-ce-cli`, `docker-buildx-plugin`, `docker-compose-plugin` и все зависимости системных пакетов. Проверьте их подписи/хеши в доверенном процессе переноса; установите локально `sudo apt-get --no-download install /srv/packages/*.deb`. Комплект приложения не содержит пакеты ОС; недостающая зависимость должна остановить подготовку, а не вызвать скачивание.
3. Запустите `sudo systemctl enable --now docker`; проверьте `python3 --version`, `sudo docker version`, `sudo docker compose version`, `uname -m`. Проверка deploy не устанавливает и не обновляет ОС автоматически.
4. В корпоративном DNS задайте, например, `it29.example.internal` и отдельный `it29-staging.example.internal`. В сертификате корпоративного CA должен быть SAN точного имени. Получите `fullchain.pem` (серверный сертификат и промежуточные CA) и `privkey.pem`. Закрытый ключ создаётся и остаётся внутри сети. Корневой CA установите также на рабочих местах пользователей.
5. SSH/22 разрешите только административной подсети, production HTTPS/443 — разрешённым клиентским подсетям. PostgreSQL/5432, API/8000 и frontend/80 наружу не публикуются. Docker-публикация портов может обходить UFW: примените согласованные фильтры Docker/DOCKER-USER или сетевой firewall и проверьте доступ с отдельного клиента. См. [Docker: firewall](https://docs.docker.com/engine/network/packet-filtering-firewalls/). Не отключайте Docker iptables и не публикуйте Docker API.

Для staging по умолчанию указан `127.0.0.1:8443`: он доступен локально или через SSH tunnel. При проверке с отдельного тестового клиента укажите адрес выделенного интерфейса и разрешите его на firewall. Не используйте production данные в staging.

## 2. Подготовить каталоги и распаковать

Примеры ниже используют production; заменяйте имя контура согласованно во всех путях. В `/srv/element29/incoming` должны лежать только перенесённый архив и доверенные bootstrap-файлы из RELEASE.md.

```bash
sudo install -d -m 0750 /srv/element29/releases
sudo install -d -m 0700 /etc/element29 /etc/element29/tls-production
sudo install -d -m 0700 /var/lib/element29/production
sudo python3 -B /srv/element29/incoming/bootstrap/unpack-release.py \
  /srv/element29/incoming/element29-<версия>-<commit>-linux-amd64.tar.gz \
  /srv/element29/releases/<версия>-<commit> \
  --sha256 <SHA256-из-доверенного-канала>
```

Замените значения `<...>` фактическими. Проверяющий код и его библиотека должны быть удостоверены до этой команды. Каталог назначения должен отсутствовать. Распаковка сначала проверяет внешний hash, затем allowlist/пути/типы, затем SHA256 каждого файла и manifest. Не редактируйте распакованный выпуск и не помещайте в него backup, настройки или посторонние файлы; любой лишний файл вызывает отказ. Выпуск и state должны быть доступны только администратору. Python entrypoints не создают `__pycache__`.

Задайте удобную переменную пути (без секретов):

```bash
release=/srv/element29/releases/<версия>-<commit>
sudo install -m 0600 "$release/deploy/production.env.example" /etc/element29/production.env
sudo install -m 0644 /secure-transfer/fullchain.pem /etc/element29/tls-production/fullchain.pem
sudo install -m 0600 /secure-transfer/privkey.pem /etc/element29/tls-production/privkey.pem
sudo install -m 0644 /secure-transfer/corporate-root-ca.crt /usr/local/share/ca-certificates/element29-corporate.crt
sudo update-ca-certificates
sudoedit /etc/element29/production.env
```

Исправьте hostname, bind-адрес, порт и TLS-пути. `APP_ORIGINS` — JSON-массив ровно с одним точным HTTPS origin, без завершающего `/`, с портом при нестандартном порте. `POSTGRES_USER` — owner, `APP_DB_USER` — отдельная runtime-роль. Генерируйте два разных случайных секрета командой `openssl rand -hex 32` в закрытом административном терминале; вставьте их через редактор, не через аргументы команд или shell history. Не сохраняйте вывод терминала. Файл содержит простые `KEY=value`, без shell quoting, `$`, подстановок, multiline и inline-комментариев. Права root:root 0600. Не выполняйте `source production.env`.

Секреты не находятся в archive, image или Git. Они передаются контейнерам как environment; root и владельцы Docker socket способны их прочитать. Ограничьте такие права. Не публикуйте `docker inspect`, полный `compose config`, env или содержимое backup в отчётах. Текущий runner фиксирует hash config; последующее изменение настроек требует отдельной согласованной операции, а не незаметной подмены.

## 3. Первая установка и администратор

```bash
sudo bash "$release/scripts/deploy/deploy.sh" install \
  --environment production --config /etc/element29/production.env --release "$release"
sudo bash "$release/scripts/deploy/deploy.sh" create-admin \
  --environment production --config /etc/element29/production.env \
  --username admin --display-name 'Администратор'
sudo bash "$release/scripts/deploy/deploy.sh" health \
  --environment production --config /etc/element29/production.env
```

Пароль администратора вводится скрыто в интерактивном терминале; пароль не передаётся как аргумент и не хранится в браузерном storage. Команду нельзя запускать через pipe или терминал без TTY.

`install` проверяет Linux/root, права, Docker/Compose, TLS-файлы, release hashes, архитектуру, Compose и `nginx -t`, загружает `images.tar` и сверяет image ID. Затем создаёт внешние volumes `element29-production-postgres` и `element29-production-files`, ждёт PostgreSQL, запускает **ровно один отдельный процесс** `python -m alembic upgrade head`, выдаёт runtime-роль через `python -m app.cli provision-db-role` и поднимает приложения. API при старте не запускает миграции. Owner используется только PostgreSQL/ops; API использует ограниченную runtime-роль.

Readiness проходит как внутри контейнеров, так и через настоящий HTTPS с проверкой CA и имени: `/api/v1/health/ready`. `curl --resolve` проверяет локальный endpoint; отдельно проверьте DNS и доступ с рабочего места. Проверьте вход, выход, запрет операций без permissions, HttpOnly/Secure cookie и отсутствие токенов в local/session storage. Установку повторно поверх существующих volumes/state runner отклоняет. Приложение работает как uid/gid 10001; uploads сохраняются в `/app/uploads` отдельного volume. Recreate контейнеров сохраняет БД и файлы.

Uvicorn принимает proxy headers внутри закрытой Docker-сети; Nginx заменяет X-Forwarded-For на адрес непосредственного клиента и выставляет HTTPS. Граница доверия требует отсутствия опубликованного API-порта и недоверенных контейнеров во внутренней сети. При добавлении внешнего балансировщика нужно отдельно согласовать trusted proxy IP и real-IP конфигурацию; произвольной входящей цепочке X-Forwarded-For доверять нельзя.

## 4. Обновление

Сначала перенесите и распакуйте новый выпуск в новый каталог, прогоните staging с синтетическими данными и согласуйте окно недоступности. Не меняйте существующие выпущенные миграции. Не запускайте параллельно ручные ops/SQL или сторонние процессы записи: lock защищает команды runner одного контура, а не посторонние инструменты.

```bash
new_release=/srv/element29/releases/<новая-версия>-<новый-commit>
sudo bash "$new_release/scripts/deploy/deploy.sh" update \
  --environment production --config /etc/element29/production.env --release "$new_release"
```

Порядок: validate/load → остановка proxy/backend/ops для прекращения записи → `pg_dump -Fc` и архив uploads → hash-проверка полного комплекта, полное чтение файлов и `pg_restore --file=/dev/null` → запуск совместимой версии PostgreSQL 17 → отдельная миграция один раз → обновление прав → приложения → readiness/HTTPS. Только после успеха меняется `/var/lib/element29/production/current.json`. В ходе изменения схемы/БД существует `pending.json`; при сбое он сохраняется и блокирует новое обновление.

На ошибке выводятся этап и путь backup; запись не возобновляется автоматически, restore не выполняется. Чтение dump подтверждает целостность, но не заменяет репетицию восстановления на staging. Смена PostgreSQL major требует отдельной процедуры и этим runner запрещена.

## 5. Backup и ручное восстановление

```bash
sudo bash "$release/scripts/deploy/deploy.sh" backup \
  --environment production --config /etc/element29/production.env
```

Это операция с остановкой записи: после проверки backup приложение снова запускается и проверяется. Каталог `/var/lib/element29/production/backups/<UTC>/` содержит `database.dump`, `files.tar.gz`, `backup.json`, `SHA256SUMS`. Backup не включает TLS private key или env: отдельно сохраняйте их в утверждённом защищённом хранилище. Храните как минимум последнюю проверенную копию до обновления и независимую копию на другом носителе внутри сети; проверяйте восстановление и правила хранения. Автоматического удаления backup нет.

При неуспешном обновлении сначала определите текущую Alembic revision, состояние контейнеров и совместимость схемы. Если backup соответствует исходному выпуску и решено заменить текущие данные:

```bash
old_release=/srv/element29/releases/<версия-из-backup>-<commit-из-backup>
sudo bash "$old_release/scripts/deploy/deploy.sh" restore \
  --environment production --config /etc/element29/production.env \
  --release "$old_release" --backup /var/lib/element29/production/backups/<UTC>
```

Нужен TTY и точная вводимая фраза `RESTORE element29-production <версия>`. До изменения данных проверяются подтверждение, hashes, контур, БД и точное совпадение manifest. Перед заменой сохраняется дополнительный backup текущего состояния; при незавершённой операции он помечен `recovery_only` и не принимается автоматизированным restore. Затем БД заменяется согласованным dump, файлы заменяются архивом, права восстанавливаются и проверяется HTTPS. Изменения после выбранного backup будут потеряны; существующие сеансы из backup возвращаются к состоянию снимка, поэтому при необходимости отзовите их отдельно.

Восстановление **не понижает PostgreSQL binaries**: сохраняется текущий работающий patch PostgreSQL 17, а приложения возвращаются к исходному выпуску. `current.json` отражает восстановленный выпуск приложения; текущий фактический PostgreSQL image может иметь более новый patch. Следующее update явно выбирает PostgreSQL из нового выпуска. При смене major используйте отдельную процедуру восстановления, не этот runner.

Без успешной первой установки `current.json` отсутствует: автоматизированное restore требует диагностики администратором. Не удаляйте volumes или pending marker вслепую. При аварии PostgreSQL сначала восстановите работоспособность его контейнера/диска без downgrade и без возобновления записи. При непроверенном backup или несовместимой миграции остановитесь для ручного восстановления на отдельном volume. Автоматического `alembic downgrade` нет: возврат только старого образа на новую несовместимую схему запрещён. Rollback приложения допустим лишь после доказательства совместимости; обычно нужен согласованный возврат БД и файлов из одного backup.

## 6. Эксплуатация

Docker json-file logs ограничены 5 файлами по 10 MiB. Nginx access log отключён; не включайте запись URL, cookies, тел запросов, SQL-параметров или секретов. PostgreSQL настроен без DETAIL/STATEMENT/параметров ошибок (`log_error_verbosity=terse`, `log_min_error_statement=panic`, `log_statement=none`, `log_parameter_max_length_on_error=0`). Ошибки внешних команд runner показывает обобщённо, чтобы не раскрывать конфигурацию. Для диагностики используйте ограниченный административный доступ; не отправляйте необработанные журналы наружу.

Проверяйте свободный диск, UTC/NTP, сроки сертификатов, успешность backup и readiness. Обновление CA/TLS и env проводите отдельной согласованной операцией; hash config в current.json нельзя исправлять автоматически без проверки нового config. Никаких `docker system prune --volumes`, `down -v` или ручного удаления внешних volumes в штатном обслуживании. Храните предыдущий архив/manifest/commit и документацию вместе с backup. После перезагрузки restart policy запускает приложения, но не миграции.
