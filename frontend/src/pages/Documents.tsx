import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../auth';
import {
  PageHeader,
  Field,
  EmptyState,
  LoadingState,
  ErrorState,
  ConfirmDialog,
  Notice,
} from '../components/common';
import { Input, Select } from '../components/ui/input';
import { Button } from '../components/ui/button';
import { request } from '../lib/api';
import { useList, useOptions } from '../features/inventory/api';
import { DocumentCard } from '../features/inventory/DocumentCard';
import { CommandError, Pagination } from '../features/inventory/shared';
import { useCommand } from '../features/issues/state';
import {
  documentNames,
  type InventoryDocument,
  type Employee,
} from '../features/inventory/types';
export function Documents() {
  const {user} = useAuth();
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [page, setPage] = useState(0);
  const documents = useList<InventoryDocument>('/inventory/documents', {
    ...filters,
    limit: 20,
    offset: page * 20,
  });
  const employees = useOptions<Employee>('/directory/employees');
  const filter = (key: string, value: string) => {
    setFilters({ ...filters, [key]: value });
    setPage(0);
  };
  return (
    <>
      <PageHeader
        title="Складские документы"
        description="Поступления, выдачи и полные отмены ошибочных операций"
      >
        <Button variant="outline" asChild>
          <Link to="/inventory">К каталогу</Link>
        </Button>
      </PageHeader>
      <section className="rounded-xl border border-border bg-white">
        <div className="grid gap-3 border-b border-border p-5 sm:grid-cols-2 xl:grid-cols-4">
          <Field label="Тип документа">
            {(id) => (
              <Select
                id={id}
                value={filters.document_type ?? ''}
                onChange={(e) => filter('document_type', e.target.value)}
              >
                <option value="">Все типы</option>
                {Object.entries(documentNames).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Дата с">
            {(id) => (
              <Input
                id={id}
                type="date"
                value={filters.date_from ?? ''}
                onChange={(e) => filter('date_from', e.target.value)}
              />
            )}
          </Field>
          <Field label="Дата по">
            {(id) => (
              <Input
                id={id}
                type="date"
                value={filters.date_to ?? ''}
                onChange={(e) => filter('date_to', e.target.value)}
              />
            )}
          </Field>
          <Field label="Отмена">
            {(id) => (
              <Select
                id={id}
                value={filters.cancelled ?? ''}
                onChange={(e) => filter('cancelled', e.target.value)}
              >
                <option value="">Все документы</option>
                <option value="false">Не отменены</option>
                <option value="true">Отменены</option>
              </Select>
            )}
          </Field>
          <Field label="Получатель">
            {(id) => (
              <Select
                id={id}
                value={filters.recipient_employee_id ?? ''}
                onChange={(e) =>
                  filter('recipient_employee_id', e.target.value)
                }
              >
                <option value="">Все получатели</option>
                {employees.data?.map((employee) => (
                  <option key={employee.id} value={employee.id}>
                    {employee.full_name} · {employee.personnel_number}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={filters.created_by_id===user?.id} onChange={event=>filter('created_by_id',event.target.checked?user!.id:'')}/>Только мои операции</label>
        </div>
        {documents.isPending ? (
          <LoadingState />
        ) : documents.error ? (
          <ErrorState
            error={documents.error}
            onRetry={() => void documents.refetch()}
          />
        ) : !documents.data.items.length ? (
          <EmptyState
            title="Документов пока нет"
            description="Измените фильтры или проведите первую складскую операцию."
          />
        ) : (
          <ul className="divide-y divide-border">
            {documents.data.items.map((document) => (
              <li
                key={document.id}
                className="flex flex-wrap justify-between gap-3 p-5 text-sm"
              >
                <div className="min-w-0 break-words">
                  <Link
                    className="font-semibold text-primary hover:underline"
                    to={`/inventory/documents/${document.id}`}
                  >
                    {document.number}
                  </Link>
                  <p className="mt-1 text-muted">
                    {documentNames[document.document_type]} ·{' '}
                    {document.document_date} ·{' '}
                    {document.recipient_name ?? document.created_by_name}
                  </p>
                </div>
                {document.is_cancelled && <span>Отменён</span>}
              </li>
            ))}
          </ul>
        )}
        <Pagination
          page={page}
          total={documents.data?.total ?? 0}
          onChange={setPage}
        />
      </section>
    </>
  );
}
export function DocumentDetails() {
  const { id } = useParams();
  const { user } = useAuth();
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');
  const query = useQuery({
    queryKey: ['warehouse', 'document', id],
    queryFn: ({ signal }) =>
      request<InventoryDocument>(`/inventory/documents/${id}`, { signal }),
  });
  const command = useCommand(
    `cancel:${id}`,
    `/inventory/documents/${id}/cancel`,
  );
  async function cancel() {
    const result = await command.send({ reason });
    setOpen(false);
    if (result) {
      await client.invalidateQueries({ queryKey: ['warehouse'] });
      void client.invalidateQueries({ queryKey: ['dashboard'] });
    }
  }
  if (query.isPending) return <LoadingState />;
  if (query.error)
    return (
      <ErrorState error={query.error} onRetry={() => void query.refetch()} />
    );
  const document = query.data;
  return (
    <>
      <PageHeader
        title="Документ склада"
        description="Сохранённые реквизиты и движения документа"
      >
        <Button variant="outline" asChild>
          <Link to="/inventory/documents">Все документы</Link>
        </Button>
      </PageHeader>
      <div className="space-y-4">
        <DocumentCard document={document} />
        <CommandError error={command.error} />
        {command.result && (
          <Notice success>
            Операция отменена. Создан компенсирующий документ{' '}
            {command.result.number}.
          </Notice>
        )}
        {command.locked && !command.pending && (
          <Notice>
            <div>
              <p>
                Результат операции пока неизвестен. Повтор сохранит прежнюю
                причину и ключ.
              </p>
              <Button className="mt-3" onClick={() => void cancel()}>
                Повторить отправку
              </Button>
            </div>
          </Notice>
        )}
        {user?.permissions.includes('inventory.manage') &&
          !document.is_cancelled &&
          document.document_type !== 'reversal' && (
            <Button
              variant="destructive"
              disabled={command.locked}
              onClick={() => setOpen(true)}
            >
              Отменить документ
            </Button>
          )}
      </div>
      <ConfirmDialog
        open={open}
        onClose={() => setOpen(false)}
        title="Отменить ошибочный документ"
        description="Отмена полностью компенсирует исходную операцию. Это не оформление фактического возврата."
        pending={command.pending}
      >
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            void cancel();
          }}
        >
          <Field label="Причина отмены">
            {(fieldId) => (
              <Input
                id={fieldId}
                required
                maxLength={1000}
                disabled={command.locked}
                value={reason}
                onChange={(event) => setReason(event.target.value)}
              />
            )}
          </Field>
          <CommandError error={command.error} />
          <Button
            variant="destructive"
            disabled={command.locked || !reason.trim()}
            type="submit"
          >
            Подтвердить отмену
          </Button>
        </form>
      </ConfirmDialog>
    </>
  );
}
