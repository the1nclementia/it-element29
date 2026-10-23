# Предложение миграции смешанных документов

Статус: подготовлено для узкого согласования, не применено.

## Причина

Текущая схема допускает в `inventory_documents` только `receipt`, `issue` и
`reversal`, а в `inventory_drafts` — только `receipt` и `issue`. Смешанный
документ должен хранить количественные строки расходников и выбранные UUID
физических экземпляров в одной транзакции и с одним idempotency result. Без
изменения этих двух CHECK-ограничений сервер не сможет безопасно добавить
`return`, `replacement` и `transfer`.

Существующие строки, документы, движения, фото и черновики не переписываются и
не удаляются. Старые миграции остаются неизменными.

## Точный DDL новой forward-миграции

Новая ревизия после `0007_equipment_instances` должна выполнить только такие
операции над ограничениями:

```sql
ALTER TABLE inventory_documents
  DROP CONSTRAINT ck_inventory_documents_valid_type;

ALTER TABLE inventory_documents
  ADD CONSTRAINT ck_inventory_documents_valid_type
  CHECK (document_type IN (
    'receipt', 'issue', 'reversal', 'return', 'replacement', 'transfer'
  ));

ALTER TABLE inventory_drafts
  DROP CONSTRAINT ck_inventory_drafts_valid_type;

ALTER TABLE inventory_drafts
  ADD CONSTRAINT ck_inventory_drafts_valid_type
  CHECK (document_type IN ('receipt', 'issue', 'return', 'replacement', 'transfer'));
```

В Alembic это будет `op.drop_constraint(..., type_="check")` и
`op.create_check_constraint(...)`. `downgrade()` останется запрещённым. Перед
применением миграции тест проверит, что на базе `0007` новые типы отклоняются, а
старые типы по-прежнему принимаются.

## Матрица разрешений

| Операция | Существующее право | Дополнительное право для UUID экземпляров |
| --- | --- | --- |
| Количественное поступление | `inventory.manage` | нет |
| Поступление с экземплярами | `inventory.manage` | `equipment.manage` |
| Количественная выдача | `inventory.issue` | нет |
| Выдача с экземплярами | `inventory.issue` | `equipment.manage` |
| Возврат экземпляра | — | `equipment.manage` |
| Замена (возврат + новая выдача) | `inventory.issue` | `equipment.manage` |
| Перемещение экземпляров | `movements.manage` | `equipment.manage` |
| Чтение количественных документов | `inventory.read` | нет |
| Чтение строк экземпляров | `inventory.read` | `equipment.read` |

Проверка дополнительных прав выполняется сервером непосредственно перед
блокировкой строк. Роль `storekeeper` не получает `equipment.manage` автоматически;
роль `it_specialist` не получает `inventory.manage` автоматически. Для операции
смешанного документа требуются оба явно выданных permission.

## Границы первой реализации

- Новые типы документов не появляются в API до применения этой миграции.
- Existing `receipt/issue` остаются количественными и продолжают отклонять
  serialized-позиции кодом `serialized_item_requires_instance_document`.
- В одной строке не смешиваются количество и UUID: количественная строка имеет
  `quantity`, строка экземпляра — один `equipment_instance_id`.
- Движения расходников остаются только в `inventory_movements`; состояние
  экземпляра изменяется в общей транзакции через будущий `equipment_movements`.
- Возвраты, замены и перемещения не реализуются этой подготовительной записью.
