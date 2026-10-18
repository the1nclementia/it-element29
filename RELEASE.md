# Автономный выпуск с Windows

Комплект переносит этапы 1–2 на Ubuntu 24.04. Корпоративные базы, пользовательские файлы и секреты остаются внутри корпоративной сети. Для сборки нужны Windows, PowerShell 7, Git, Python 3.12+ и Docker Desktop в режиме Linux containers с Buildx. Сервер не собирает приложение и не обращается к registry.

## 1. Подготовить проверенный commit

Выполните проверки из README, включая PostgreSQL и контейнерные проверки. Обновите PROGRESS.md, проверьте diff и создайте локальный commit. `git status --porcelain --untracked-files=all` должен быть пустым. Выпуск собирается через `git archive HEAD`, поэтому незакоммиченные изменения не попадут в образы. Версия обозначает конкретный проверенный commit; повторное использование версии для другого commit запрещено организационно.

Dockerfile приложения использует версии базовых образов и lock-файлы зависимостей; это не обещание побитового повторения сборки. Идентичность уже собранного выпуска фиксируют image ID, manifest и SHA256. Для воспроизведения работы храните исходный архив выпуска.

## 2. Выбрать архитектуру и инфраструктурные образы

На сервере `uname -m`: `x86_64` соответствует `linux/amd64`, `aarch64` — `linux/arm64`. Не переносите Windows images. Проверьте версии PostgreSQL 17 и Nginx в своей процедуре сопровождения. Ниже примеры известных версий; digest нужно получить из доверенного registry, не копировать произвольный digest из сообщения.

```powershell
docker pull --platform linux/amd64 postgres:17.11-alpine
docker pull --platform linux/amd64 nginx:1.30.6-alpine
docker image inspect postgres:17.11-alpine --format '{{json .RepoDigests}}'
docker image inspect nginx:1.30.6-alpine --format '{{json .RepoDigests}}'
```

Запишите проверенные ссылки в форме `postgres:17.11-alpine@sha256:<64 hex>` и `nginx:1.30.6-alpine@sha256:<64 hex>`. Сборщик требует одновременно версию и digest; `latest` и плавающие инфраструктурные ссылки не принимаются.

## 3. Собрать архив

```powershell
pwsh -File .\scripts\release\build-release.ps1 `
  -Version '0.1.0-stage2' `
  -OutputDirectory 'D:\Releases\element29-0.1.0-stage2' `
  -Platform 'linux/amd64' `
  -PostgresImage 'postgres:17.11-alpine@sha256:<проверенный digest>' `
  -NginxImage 'nginx:1.30.6-alpine@sha256:<проверенный digest>' `
  -Python '.\.venv\Scripts\python.exe'
```

Замените значения в угловых скобках. Скрипт проверит чистоту Git, соберёт backend/frontend через Buildx `--platform --load`, загрузит инфраструктурные образы и сохранит все четыре через `docker save`. Имена имеют вид `element29/backend:0.1.0-stage2-<12 символов commit>`. Каталог результата не должен существовать.

Результат: `element29-<версия>-<commit>-linux-amd64.tar.gz`, соседний `.sha256` и `manifest.json`. Внутри архива:

- `images.tar` с четырьмя Linux-образами;
- серверный Compose, Nginx TLS, примеры настроек без секретов;
- Linux deploy/backup/restore и строгая проверка архива;
- RELEASE.md, DEPLOYMENT.md, manifest и SHA256SUMS.

Исходники репозитория, `.env`, Git, uploads и базы не входят в allowlist. Manifest содержит версию, полный commit, платформу, PostgreSQL major, точные image ID и исходные ссылки/digest. Проверка отвергает лишние файлы, ссылки, traversal и повторные пути. Архив ограничен 30 GiB распакованного содержимого.

## 4. Передать внутрь сети

Используйте согласованный носитель или SSH/SCP. Отдельно передайте SHA256 архива по доверенному каналу; соседний файл checksum сам по себе не доказывает происхождение. Не отправляйте корпоративные данные в облако.

Для первой распаковки передайте из того же проверенного commit два bootstrap-файла: `scripts/deploy/unpack-release.py` и `scripts/deploy/release_lib.py`. Проверьте их SHA256 отдельно до запуска: архив не может сам удостоверять исполняемый проверяющий код. Последующие выпуски можно распаковывать уже доверенным проверяющим скриптом предыдущего выпуска при совместимом формате.

```powershell
Get-FileHash .\scripts\deploy\unpack-release.py -Algorithm SHA256
Get-FileHash .\scripts\deploy\release_lib.py -Algorithm SHA256
scp 'D:\Releases\element29-0.1.0-stage2\*.tar.gz*' deploy@server:/srv/element29/incoming/
scp .\scripts\deploy\unpack-release.py .\scripts\deploy\release_lib.py deploy@server:/srv/element29/incoming/bootstrap/
```

Сначала подтвердите SSH fingerprint сервера у администратора. Не отключайте проверку host key. На сервере следуйте DEPLOYMENT.md: сначала staging и репетиция восстановления, затем production.

## Граница проверки

Сценарные pytest проверяют валидатор, путь отказов, порядок миграций и отсутствие автоматического восстановления. Это не заменяет запуск образов, восстановление реального тестового dump и проверку целевого Ubuntu-сервера. Результат конкретного прогона и оставшиеся ограничения записываются в PROGRESS.md. До релиза нужно проверить HTTPS, вход, RBAC, восстановление БД и файлов в отдельном контуре.

Воспроизводимая репетиция на Windows с Docker Desktop и OpenSSL (из Git for Windows):

```powershell
.\.venv\Scripts\python.exe -m pytest scripts/tests -q -p no:cacheprovider --basetemp=.scratch/release-tests
.\.venv\Scripts\python.exe scripts/tests/rehearse_docker.py --run `
  --backend-image element29/backend:0.1.0-acceptance `
  --frontend-image element29/frontend:0.1.0-acceptance
```

Образы acceptance должны быть предварительно собраны из проверяемых исходников; локально также нужны `postgres:17.11-alpine` и `nginx:1.30.6-alpine`. Harness использует только проект `e29-release-test`, отказывается работать при существующих его контейнерах/volumes и публикует временный HTTPS на `127.0.0.1:19443`. Он сохраняет/загружает образы, проверяет реальный install/update, целостность dump и файлов, явный restore, возврат изменённой строки/файла и HTTPS readiness с тестовым CA. В конце удаляет только свои контейнеры и volumes; синтетические артефакты остаются в игнорируемом `.scratch/release-live-*`. В manifest репетиции указан тестовый snapshot; это не официальный выпуск из чистого commit.

Адаптер заменяет Windows/Linux пути и вызов Docker CLI, но использует настоящий deployment state machine и контейнеры Linux. Он не проверяет Ubuntu host preflight, права root/0600, flock, systemd, корпоративный DNS/CA и firewall. Эти пункты принимаются отдельно на выделенном Ubuntu staging. Формальная сборка `build-release.ps1` из чистого commit — отдельная проверка после завершения коммита.
