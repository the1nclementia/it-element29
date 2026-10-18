# Этап 3 — склад и выдача

Дата: 18.10.2026. Основание — полное задание пользователя «реализовать этап 3».
Baseline: `5b278c03352142f100671ecbe2a1243306f33d7a`, main, рабочее дерево до этапа чистое.
HEAD совпал с указанным в задании; этапы 1–2 и deployment уже зафиксированы пользователем.
Исходные migrations 0001/0002 неизменяемы. Действующие контейнеры element29, их БД,
files и .env не изменяются. Рабочий результат готовится отдельно, без production deploy.

## Границы

Один логический склад, целые штуки, позиции с UUID и стабильным internal_code.
Каталог, производители, категории, модели принтеров, совместимость, фото,
поступление/начальный остаток, выдача сотруднику, полная отмена, чтение документов.
Минимальные departments/employees CRUD с архивированием; User — оператор, Employee — получатель.
Нет возврата, частичной отмены, цен, резервов, партий, физических единиц или этапов 4–8.

## Схема

Новая добавочная migration 0003_inventory после 0002_identity. Таблицы:

- manufacturers: RecordMixin, name, name_key unique, version default 1.
- inventory_categories: RecordMixin, code unique immutable, name, version. Системный
  код `cartridges` (Картриджи) добавляется без позиций/остатков.
- printer_models: RecordMixin, manufacturer_id FK, model, model_key,
  UNIQUE(manufacturer_id, model_key), version.
- inventory_items: RecordMixin, internal_code unique immutable, category_id,
  manufacturer_id, model, article nullable, description, min_stock >=0, version.
- inventory_compatibilities: UUID, item/model FK RESTRICT, unique pair, archived_at;
  существующие связи архивируются/восстанавливаются без DELETE.
- inventory_documents: UUID, number unique, document_type receipt/issue/reversal,
  created_at UTC, document_date, created_by_id, recipient_employee_id nullable,
  recipient_name / recipient_personnel_number / recipient_department (снимки), comment,
  receipt_purpose delivery/opening_balance nullable, external_number nullable,
  reversal_of_id unique FK, reason nullable, idempotency_key UUID, request_hash SHA256.
  UNIQUE(created_by_id, document_type, idempotency_key). Номер из отдельной sequence
  inventory_document_number_seq: INV-0000000001; пропуски при rollback допустимы.
- inventory_document_items: UUID, document_id, inventory_item_id, quantity BIGINT>0,
  line_number>0, internal_code/model/manufacturer/unit (снимки), unique doc/item и doc/line.
  Дополнительный unique(id, inventory_item_id) — цель составного FK движения.
- inventory_movements: UUID, document_item_id unique, inventory_item_id,
  delta BIGINT !=0, occurred_at UTC, reversal_of_id unique FK self.
  Составной FK (document_item_id, inventory_item_id) исключает несовпадение позиции.
- file_attachments: UUID, storage_key unique, mime_type, size, sha256, width, height,
  uploaded_by_id, created_at.
- inventory_item_attachments: UUID, inventory_item_id, file_attachment_id, position,
  is_primary, archived_at; unique pair, partial unique active primary per item.

Department/Employee получают добавочную version default1, прежние записи сохраняются.
Все исторические FK RESTRICT. Документы/строки/движения неизменяемы, без RecordMixin.
Все FK индексированы; ledger (item_id, occurred_at, id), документы по времени/типу/
получателю, обе стороны совместимости, активные позиции/код/модель. Поиск небольшого
каталога использует ILIKE с escaped LIKE-символами, без расширений PostgreSQL.

## Транзакции и порядок блокировок

READ COMMITTED, существующий statement_timeout=3000 сохраняется. Сервисы используют
уже открытую request Session и делают один явный commit, без вложенного begin.

Порядок: advisory lock конкретного ключа идемпотентности → справочники в стабильном
порядке (departments → employees; каталог manufacturer → category → printer model) →
inventory_items по UUID FOR UPDATE → shared advisory auth-lock (29,2) → User FOR SHARE
→ исходная AuthSession FOR SHARE → повторная проверка активности/permission/expiry.
Shared auth-lock совместим с другими складскими операциями и синхронизируется с
существующим exclusive lock смены роли/пароля; это не глобальный mutex склада.
Он берётся ПОСЛЕ ожидания item-lock, чтобы отзыв сессии во время ожидания успел вступить в силу.
Logout сериализуется блокировкой исходной session-строки. Auth/admin не блокирует складские строки.

Получатель: сначала прочитать department_id, затем блокировать подразделение и сотрудника,
перечитать; при сменившемся department_id вернуть контролируемый повтор, не нарушать порядок.
Перевод/архив сотрудника использует тот же порядок. Архив подразделения с активными
сотрудниками запрещён. Архив производителя не блокирует выдачу уже существующей позиции.

После item-lock отдельным запросом SUM(delta) по всем позициям. Строго целые quantity
1..1_000_000, max100 строк, повтор item_id запрещён. Общий остаток ограничен точным JS
integer 9_007_199_254_740_991. Нет отрицательного остатка и частичного проведения.
Документ, строки, ledger и аудит создаются одной транзакцией; сбой откатывает всё.
Архив позиции допустим только при нулевом остатке под item-lock. Отмена выдачи может
вернуть положительный остаток архивной позиции: автоматическое восстановление с аудитом.

Idempotency-Key UUID обязателен для receipt/issue/cancel. Advisory key — стабильный
64-bit hash автора, команды и UUID. После ожидания повторно ищется результат.
Хеш нормализованного payload (UUID, ISO date, строки по UUID, stripped текст); порядок
строк не влияет на равенство команды. Повтор требует текущих прав и возвращает 200,
первое проведение 201; другое содержимое 409 idempotency_conflict.
Отмена после item-lock перечитывает существующую reversal; unique FK защищает от повторов.
UPDATE на документы ради блокировки не выдаётся. Отмена отмены запрещена.

Lock timeout/deadlock: rollback, безопасный временный ответ `operation_busy`, можно
повторить тот же ключ; SQL/параметры не раскрываются.

## API-контракт для frontend/backend

Префикс /api/v1, существующий detail.code/message. Списки `{items:[],total:number}`,
offset>=0, limit1..100 default20, q<=100. `archived`=false(default), true, либо `all`.
Для редактируемых справочников response включает id, version, archived_at, created_at,
updated_at и свои поля. PATCH получает version. archive/restore POST `{version}`.
Codes canonical uppercase для internal_code; категорий lowercase, системный cartridges.

Справочники list/create/PATCH/{id}/archive/restore:

- /inventory/manufacturers: name.
- /inventory/categories: code,name (code только create).
- /inventory/printer-models: manufacturer_id,model; response manufacturer_name.
- /directory/departments: code,name.
- /directory/employees: personnel_number,full_name,department_id; response department_name.

Каталог /inventory/items: GET/POST; /{id} GET/PATCH; /{id}/archive и /restore.
Payload create: internal_code,category_id,manufacturer_id,model,article?,description?,min_stock=0.
PATCH те же изменяемые поля плюс version, без internal_code. Item response: эти поля,
id/version/archived_at/created_at/updated_at, category_name,manufacturer_name,
balance:int,unit:"pcs",is_low_stock:bool,primary_photo_url:string|null.
Фильтры: q,category_id,manufacturer_id,printer_model_id,in_stock:bool,low_stock:bool,
archived,sort=code|model|balance (default code),direction=asc|desc,offset,limit.
/{id}/compatibilities GET `{items:[PrinterModel],total}`; PUT `{version,printer_model_ids:UUID[]}`
возвращает обновлённый Item. Max100, дубли запрещены. Архивные ссылки не удаляются.

POST /inventory/receipts: `{document_date,receipt_purpose,external_number?,comment?,items:[{inventory_item_id,quantity}]}`.
POST /inventory/issues: `{document_date,recipient_employee_id,comment?,items:[...]}`.
POST /inventory/documents/{id}/cancel: `{reason}`. Все требуют Idempotency-Key.
Документ response: id,number,document_type,document_date,created_at,created_by_id,
created_by_name,recipient_employee_id,recipient_name,recipient_personnel_number,
recipient_department,comment,receipt_purpose,external_number,reversal_of_id,reason,
is_cancelled,reversal_id,reversal_number,items:[{id,line_number,inventory_item_id,
quantity,internal_code,model,manufacturer,unit,delta}].
GET /inventory/documents filters document_type,recipient_employee_id,created_by_id,
date_from/date_to (document_date inclusive),cancelled:bool,offset,limit; newest created_at/id.
GET /inventory/documents/{id} detail. GET /inventory/items/{id}/movements paginated:
`{items:[{id,document_id,document_number,document_type,delta,occurred_at,reversal_of_id}],total}`.
Insufficient stock: 409 detail.code=insufficient_stock, message +
`items:[{inventory_item_id,available,requested}]`. ApiError сохраняет detail для UI.

Photos /inventory/items/{id}/photos GET `{items:[Photo],total}`, POST multipart `file`.
Photo: id (=FileAttachment.id, используется как attachment_id),content_url,position,
is_primary,width,height,mime_type,size,archived_at. POST201; PATCH /{attachment_id}
`{is_primary?:true,position?:int>=0}` возвращает Photo; POST /{attachment_id}/archive204.
GET /{attachment_id}/content отдаёт нормализованное изображение с no-store/nosniff.

## Права и аудит

inventory.read: каталог, документы, движения, фото и чтение recipients.
inventory.manage: каталог, совместимость, фото, receipt и cancel.
inventory.issue: выдача. Новое directory.manage только administrator, additive seed.
Existing IT Specialist получает чтение/выдачу; Manager только чтение.
Runtime: mutable справочники SELECT/INSERT/UPDATE без DELETE; документы/строки/ledger/
file metadata SELECT/INSERT; связи SELECT/INSERT/UPDATE; audit SELECT/INSERT;
sequence USAGE. Старые auth grants сохраняются, DDL запрещён.

Аудит расширяется только IDs/кодами изменённых полей и безопасными метаданными команд,
не full payload/ФИО/бинарными данными. Снимки получателя — только документ.
Имена событий inventory.*, directory.*, photo.* явно отображаются на Dashboard.
Метрики: cartridges balance активных позиций категории cartridges; issues_today —
число неотменённых issue по created_at за текущий день Asia/Yekaterinburg;
low_stock — count active min_stock>0 && balance<min_stock. Остальные метрики null.

## Фото и файловая система

Config: uploads_dir=/app/uploads, photo_max_bytes=5MiB, photo_max_pixels=20_000_000,
photo_max_per_item=5. JPEG/PNG/WebP только после проверки заявленного MIME и реального
формата/декодирования, EXIF transpose, перекодирование без метаданных. MIME mismatch415.
Размер ограничен на ASGI receive до multipart parsing и при чтении chunkами.
Сгенерированный storage_key; basename/resolve/no-symlinks; пользовательское filename не путь.
Записать временный файл → fsync/атомарное помещение → commit metadata/link. При отказе
не менять старые файлы; возможный orphan остаётся для отдельной readonly диагностики.
Архивирование связи не удаляет файл. Главный снимок защищён item-lock/partial unique;
при архивировании главного выбрать первый активный по position/id. Файл доступен только
по активной типизированной связи и inventory.read, никакого публичного uploads location.

## UI

Существующий стиль/компоненты сохраняются. Inventory: каталог, фильтры, карточка,
совместимость/галерея/движения, управление справочниками и поступление, документы.
Issues: корзина только в памяти, добавление суммирует, сотрудник/дата/комментарий,
подтверждение. Пока результат неизвестен, payload+ключ сохраняются неизменными для
повтора; новый ключ только для новой осознанной операции. Ошибка не очищает корзину.
Document detail и отмена с причиной доступны из каталога; Manager читает документы,
но не видит рабочую выдачу. Directory UI только admin, навигация по permission.
Multipart транспорт не устанавливает Content-Type вручную, JSON вызовы не ломаются.
Использовать same-origin content_url фото; blob preview не обязателен, CSP не ослаблять.

## Безопасная приёмка

Не выполнять прежние TRUNCATE/downgrade/DROP даже для старых тестов. Отдельный новый
test Compose project, PostgreSQL без опубликованных портов; fixture не читает .env,
использует отдельные TEST_* параметры, проверяет контрольный marker кластера и создаёт
новую случайную БД на тест. Только CREATE + forward Alembic. Никакого reset старой БД.
Тесты readiness используют пустую новую БД до migration и ту же после upgrade.
Runtime grants проверяются через has_table_privilege/has_schema_privilege и разрешённые
реальные команды, без попыток DELETE/DROP. Синтетические данные сохраняются до остановки
только нового disposable test-контура. Не удалять действующие volumes.
Отдельный acceptance стенд stage3, новый postgres/files, runtime-роль, auth и warehouse E2E.

## Будущее сканирование (не реализуется сейчас)

inventory_units с item_id описывает физическую единицу. Идентификаторы имеют тип,
нормализованное уникальное значение и типизированного владельца item/unit; пропуска
отдельно ссылаются на employees. Связи unit → document_item типизированы.
Штрихкод модели может означать SKU, не единицу; пропуск выбирает получателя, не логинит
оператора. Сканер вызывает те же команды, permissions, idempotency и подтверждение.
Привязка units к уже существующему остатку не создаёт receipt; ledger остаётся источником
количества. В unit-режиме quantity равно числу units; переход сверяет остаток и единицы
под item-lock, без скрытой корректировки. Смешанный режим требует явного количества
неидентифицированных штук и правил; до их принятия переход запрещён. Неизвестный или
неоднозначный код не создаёт сущности и не проводит документ автоматически.
