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
export function StockForm({ kind }: { kind: 'receipt' | 'issue' }) {
  const client = useQueryClient();
  const basket = useDraft(kind);
  const { draft, update } = basket;
  const command = useCommand(
    kind,
    kind === 'issue' ? '/inventory/issues' : '/inventory/receipts',
  );
  const [confirm, setConfirm] = useState(false);
  const [validation, setValidation] = useState('');
  const employees = useOptions<Employee>('/directory/employees');
  const locked = command.locked || command.pending;
  const payload = () => ({
    document_date: draft.date,
    comment: draft.comment,
    ...(kind === 'issue'
      ? { recipient_employee_id: draft.employee }
      : { receipt_purpose: draft.purpose, external_number: draft.external }),
    items: draft.lines.map((line) => ({
      inventory_item_id: line.item.id,
      quantity: line.quantity,
    })),
  });
  async function send() {
    const result = await command.send(payload());
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
        <Button variant="outline" asChild>
          <Link to="/inventory">К каталогу</Link>
        </Button>
      </PageHeader>
      <div className="mb-5 space-y-3">
        <CommandError error={command.error} lines={draft.lines} />
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
                      required
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
            <Button type="submit" disabled={locked || !draft.lines.length}>
              {command.pending
                ? 'Отправляем…'
                : kind === 'issue'
                  ? 'Проверить выдачу'
                  : 'Проверить поступление'}
            </Button>
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
        pending={command.pending}
      >
        <div className="space-y-4">
          <p className="break-words text-sm">
            {kind === 'issue'
              ? employees.data?.find(
                  (employee) => employee.id === draft.employee,
                )?.full_name
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
          <Button disabled={command.pending} onClick={() => void send()}>
            {kind === 'issue'
              ? 'Подтвердить выдачу'
              : 'Подтвердить поступление'}
          </Button>
        </div>
      </ConfirmDialog>
    </>
  );
}
