import { useState, type FormEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import {
  PageHeader,
  Field,
  Notice,
  ConfirmDialog,
  EmptyState,
  ErrorState,
} from '../../components/common';
import { Button } from '../../components/ui/button';
import { Input, Select } from '../../components/ui/input';
import { Catalog } from '../inventory/Catalog';
import { DocumentCard } from '../inventory/DocumentCard';
import { CommandError } from '../inventory/shared';
import { useOptions } from '../inventory/api';
import type { Employee } from '../inventory/types';
import { useCommand, useDraft } from './state';
import type { ServerDraft } from './drafts';
export function StockForm({ kind }: { kind: 'receipt' | 'issue' }) {
  const client = useQueryClient();
  const basket = useDraft(kind);
  const { draft, update } = basket;
  const command = useCommand(
    kind,
    kind === 'issue' ? '/inventory/issues' : '/inventory/receipts',
  );
  const saveCommand = useCommand<ServerDraft>(
    `save:${kind}`,
    '/inventory/drafts',
  );
  const [confirm, setConfirm] = useState(false);
  const [validation, setValidation] = useState('');
  const employees = useOptions<Employee>('/directory/employees');
  const locked = basket.locked || command.pending || saveCommand.pending;
  const payload = () => ({
    document_date: draft.date || null,
    comment: draft.comment,
    ...(kind === 'issue'
      ? {
          recipient_employee_id: draft.employee || null,
          recipient_name: draft.employee ? null : draft.recipientName || null,
          recipient_building: draft.recipientBuilding || null,
          recipient_department: draft.recipientDepartment || null,
          recipient_room: draft.room || null,
        }
      : {
          receipt_purpose: draft.purpose,
          external_number: draft.external,
          supplier_name: draft.supplier || null,
        }),
    items: draft.lines.map((line) => ({
      inventory_item_id: line.item.id,
      quantity: line.quantity,
    })),
  });
  async function save() {
    if (
      draft.lines.some(
        (line) =>
          !Number.isInteger(line.quantity) ||
          line.quantity < 1 ||
          line.quantity > 1000000,
      )
    ) {
      setValidation(
        'Для сохранения укажите целое количество от 1 до 1 000 000.',
      );
      return undefined;
    }
    const result = await saveCommand.send(
      draft.saved
        ? { version: draft.saved.version, payload: payload() }
        : { id: crypto.randomUUID(), document_type: kind, payload: payload() },
      draft.saved ? `/inventory/drafts/${draft.saved.id}` : '/inventory/drafts',
      draft.saved ? 'PATCH' : 'POST',
    );
    if (result) {
      basket.remember({ id: result.id, version: result.version });
      await client.invalidateQueries({ queryKey: ['warehouse'] });
    }
    return result;
  }
  async function send() {
    let result;
    if (command.locked) result = await command.send(payload());
    else if (draft.saved) {
      const saved = await save();
      if (!saved) {
        setConfirm(false);
        return;
      }
      result = await command.send(
        { version: saved.version },
        `/inventory/drafts/${saved.id}/post`,
      );
    } else result = await command.send(payload());
    setConfirm(false);
    if (result) {
      basket.clear();
      await client.invalidateQueries({ queryKey: ['warehouse'] });
      void client.invalidateQueries({ queryKey: ['dashboard'] });
    }
  }
  function review(event: FormEvent) {
    event.preventDefault();
    setValidation('');
    if (
      !draft.lines.length ||
      draft.lines.length > 100 ||
      draft.lines.some(
        (line) =>
          !Number.isInteger(line.quantity) ||
          line.quantity < 1 ||
          line.quantity > 1000000,
      )
    ) {
      setValidation(
        'Добавьте от 1 до 100 позиций. Количество — целое число от 1 до 1 000 000.',
      );
      return;
    }
    setConfirm(true);
  }
  return (
    <>
      <PageHeader
        title={kind === 'issue' ? 'Выдача' : 'Поступление'}
        description={
          kind === 'issue'
            ? 'Выберите расходные материалы и сотрудника-получателя'
            : 'Поставка или ввод начальных остатков одним документом'
        }
      >
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" asChild>
            <Link to="/inventory/drafts">Мои черновики</Link>
          </Button>
          <Button variant="outline" asChild>
            <Link to="/inventory">К каталогу</Link>
          </Button>
        </div>
      </PageHeader>
      <div className="mb-5 space-y-3">
        <CommandError error={command.error} lines={draft.lines} />
        <CommandError error={saveCommand.error} lines={draft.lines} />
        {draft.saved && <Notice success>Черновик сохранён на сервере.</Notice>}
        {saveCommand.locked && !saveCommand.pending && (
          <Notice>
            <div>
              <p>
                Результат сохранения неизвестен. Повтор сохранит тот же черновик
                и содержимое.
              </p>
              <Button className="mt-3" onClick={() => void save()}>
                Повторить сохранение
              </Button>
            </div>
          </Notice>
        )}
        {validation && <Notice>{validation}</Notice>}
        {command.locked && !command.pending && (
          <Notice>
            <div>
              <p>
                Результат операции пока неизвестен. Данные сохранены в памяти;
                повтор отправки использует прежний ключ. Не закрывайте вкладку
                до получения результата.
              </p>
              <Button className="mt-3" onClick={() => void send()}>
                Повторить отправку
              </Button>
            </div>
          </Notice>
        )}
        {command.result && (
          <>
            <Notice success>Документ проведён.</Notice>
            <DocumentCard document={command.result} />
          </>
        )}
      </div>
      <div className="grid items-start gap-5 xl:grid-cols-2">
        <Catalog
          compact
          disabled={locked || draft.lines.length >= 100}
          onAdd={basket.add}
        />
        <section className="min-w-0 rounded-xl border border-border bg-white p-5">
          <h2 className="mb-5 text-lg font-semibold">
            {kind === 'issue' ? 'Корзина' : 'Строки поступления'}
          </h2>
          {!draft.lines.length && (
            <EmptyState
              title="Пока нет позиций"
              description="Добавьте позиции из каталога слева."
            />
          )}
          <form className="space-y-4" onSubmit={review}>
            <ul className="divide-y divide-border">
              {draft.lines.map((line) => (
                <li key={line.item.id} className="space-y-3 py-4">
                  <p className="break-words text-sm font-medium">
                    {line.item.internal_code} · {line.item.model}
                  </p>
                  <p className="text-xs text-muted">
                    На складе: {line.item.balance} шт.
                  </p>
                  <div className="flex items-end gap-3">
                    <Field label={`Количество ${line.item.internal_code}`}>
                      {(id) => (
                        <Input
                          id={id}
                          type="number"
                          required
                          min={1}
                          max={1000000}
                          step={1}
                          disabled={locked}
                          value={line.quantity || ''}
                          onChange={(e) =>
                            update({
                              lines: draft.lines.map((value) =>
                                value.item.id === line.item.id
                                  ? {
                                      ...value,
                                      quantity: Number(e.target.value),
                                    }
                                  : value,
                              ),
                            })
                          }
                        />
                      )}
                    </Field>
                    <Button
                      variant="outline"
                      type="button"
                      disabled={locked}
                      aria-label={`Убрать ${line.item.internal_code}`}
                      onClick={() =>
                        update({
                          lines: draft.lines.filter(
                            (value) => value.item.id !== line.item.id,
                          ),
                        })
                      }
                    >
                      Убрать
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
            {kind === 'issue' ? (
              <>
                <Field label="Сотрудник-получатель">
                  {(id) => (
                    <Select
                      id={id}
                      disabled={locked || !employees.data}
                      value={draft.employee}
                      onChange={(e) => update({ employee: e.target.value })}
                    >
                      <option value="">Выберите сотрудника</option>
                      {employees.data?.map((employee) => (
                        <option key={employee.id} value={employee.id}>
                          {employee.full_name} · {employee.personnel_number} ·{' '}
                          {employee.department_name}
                        </option>
                      ))}
                    </Select>
                  )}
                </Field>
                <Field
                  label="Подразделение"
                  hint="Определяется по сотруднику или вводится вручную."
                >
                  {(id) => (
                    <Input
                      id={id}
                      disabled={locked || !!draft.employee}
                      value={
                        employees.data?.find(
                          (employee) => employee.id === draft.employee,
                        )?.department_name ?? draft.recipientDepartment
                      }
                      onChange={(event) =>
                        update({ recipientDepartment: event.target.value })
                      }
                    />
                  )}
                </Field>
                <Field
                  label="ФИО получателя"
                  hint="Заполните, если сотрудника нет в справочнике."
                >
                  {(id) => (
                    <Input
                      id={id}
                      maxLength={300}
                      disabled={locked || !!draft.employee}
                      value={draft.recipientName}
                      onChange={(event) =>
                        update({ recipientName: event.target.value })
                      }
                    />
                  )}
                </Field>
                <Field label="Здание" hint="Необязательное поле.">
                  {(id) => (
                    <Input
                      id={id}
                      maxLength={200}
                      disabled={locked}
                      value={draft.recipientBuilding}
                      onChange={(event) =>
                        update({ recipientBuilding: event.target.value })
                      }
                    />
                  )}
                </Field>
                <Field label="Кабинет" hint="Необязательное поле.">
                  {(id) => (
                    <Input
                      id={id}
                      maxLength={100}
                      disabled={locked}
                      value={draft.room}
                      onChange={(event) => update({ room: event.target.value })}
                    />
                  )}
                </Field>
                {employees.error && (
                  <ErrorState
                    error={employees.error}
                    onRetry={() => void employees.refetch()}
                  />
                )}
                {employees.data?.length === 0 && (
                  <Notice>
                    Нет активных сотрудников. Администратор может добавить
                    получателя в разделе «Справочники».
                  </Notice>
                )}
              </>
            ) : (
              <>
                <Field label="Назначение поступления">
                  {(id) => (
                    <Select
                      id={id}
                      disabled={locked}
                      value={draft.purpose}
                      onChange={(e) => update({ purpose: e.target.value })}
                    >
                      <option value="delivery">Поставка</option>
                      <option value="opening_balance">Начальный остаток</option>
                    </Select>
                  )}
                </Field>
                <Field label="Поставщик" hint="Необязательное поле.">
                  {(id) => (
                    <Input
                      id={id}
                      maxLength={200}
                      disabled={locked}
                      value={draft.supplier}
                      onChange={(event) =>
                        update({ supplier: event.target.value })
                      }
                    />
                  )}
                </Field>
                <Field label="Внешний номер">
                  {(id) => (
                    <Input
                      id={id}
                      maxLength={100}
                      disabled={locked}
                      value={draft.external}
                      onChange={(e) => update({ external: e.target.value })}
                    />
                  )}
                </Field>
              </>
            )}
            <Field label="Дата документа">
              {(id) => (
                <Input
                  id={id}
                  type="date"
                  required
                  disabled={locked}
                  value={draft.date}
                  onChange={(e) => update({ date: e.target.value })}
                />
              )}
            </Field>
            <Field label="Комментарий">
              {(id) => (
                <textarea
                  id={id}
                  className="min-h-24 w-full rounded-lg border border-border p-3 text-sm"
                  maxLength={2000}
                  disabled={locked}
                  value={draft.comment}
                  onChange={(e) => update({ comment: e.target.value })}
                />
              )}
            </Field>
            <div className="flex flex-wrap gap-3">
              <Button
                type="button"
                variant="outline"
                disabled={locked}
                onClick={() => void save()}
              >
                Сохранить черновик
              </Button>
              <Button type="submit" disabled={locked || !draft.lines.length}>
                {command.pending
                  ? 'Отправляем…'
                  : kind === 'issue'
                    ? 'Проверить выдачу'
                    : 'Проверить поступление'}
              </Button>
            </div>
          </form>
        </section>
      </div>
      <ConfirmDialog
        open={confirm}
        onClose={() => setConfirm(false)}
        title={
          kind === 'issue' ? 'Подтвердить выдачу' : 'Подтвердить поступление'
        }
        description="Все строки будут проведены одним документом. Проверьте количество и реквизиты."
        pending={command.pending || saveCommand.pending}
      >
        <div className="space-y-4">
          <p className="break-words text-sm">
            {kind === 'issue'
              ? employees.data?.find(
                  (employee) => employee.id === draft.employee,
                )?.full_name || draft.recipientName
              : draft.purpose === 'opening_balance'
                ? 'Начальный остаток'
                : 'Поставка'}{' '}
            · {draft.date}
          </p>
          <ul className="space-y-2 text-sm">
            {draft.lines.map((line) => (
              <li className="break-words" key={line.item.id}>
                {line.item.internal_code} · {line.item.model} — {line.quantity}{' '}
                шт.
              </li>
            ))}
          </ul>
          <Button
            disabled={command.pending || saveCommand.pending}
            onClick={() => void send()}
          >
            {kind === 'issue'
              ? 'Подтвердить выдачу'
              : 'Подтвердить поступление'}
          </Button>
        </div>
      </ConfirmDialog>
    </>
  );
}
