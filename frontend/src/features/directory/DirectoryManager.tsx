import { useState, type FormEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  ConfirmDialog,
  EmptyState,
  ErrorState,
  Field,
  LoadingState,
  Notice,
  StatusBadge,
} from '../../components/common';
import { Button } from '../../components/ui/button';
import { Input, Select } from '../../components/ui/input';
import { request } from '../../lib/api';
import { useList, useOptions } from '../inventory/api';
import { Pagination } from '../inventory/shared';
import type { RecordEntry, Manufacturer, Department } from '../inventory/types';
type Entry = RecordEntry & Record<string, string | number | null>;
interface Definition {
  path: string;
  title: string;
  fields: {
    key: string;
    label: string;
    max?: number;
    immutable?: boolean;
    options?: 'manufacturers' | 'departments';
  }[];
}
export const definitions: Record<string, Definition> = {
  manufacturers: {
    path: '/inventory/manufacturers',
    title: 'Производители',
    fields: [{ key: 'name', label: 'Название', max: 200 }],
  },
  categories: {
    path: '/inventory/categories',
    title: 'Категории',
    fields: [
      { key: 'code', label: 'Код', max: 50, immutable: true },
      { key: 'name', label: 'Название', max: 200 },
    ],
  },
  printers: {
    path: '/inventory/printer-models',
    title: 'Модели принтеров',
    fields: [
      {
        key: 'manufacturer_id',
        label: 'Производитель',
        options: 'manufacturers',
      },
      { key: 'model', label: 'Модель принтера', max: 200 },
    ],
  },
  departments: {
    path: '/directory/departments',
    title: 'Подразделения',
    fields: [
      { key: 'code', label: 'Код', max: 50 },
      { key: 'name', label: 'Название', max: 200 },
    ],
  },
  employees: {
    path: '/directory/employees',
    title: 'Сотрудники',
    fields: [
      { key: 'personnel_number', label: 'Табельный номер', max: 50 },
      { key: 'full_name', label: 'ФИО получателя', max: 300 },
      { key: 'department_id', label: 'Подразделение', options: 'departments' },
    ],
  },
};
export function DirectoryManager({
  definition,
  manage,
}: {
  definition: Definition;
  manage: boolean;
}) {
  const client = useQueryClient();
  const [q, setQ] = useState('');
  const [archived, setArchived] = useState('false');
  const [page, setPage] = useState(0);
  const [edit, setEdit] = useState<Entry | null | undefined>();
  const [archive, setArchive] = useState<Entry>();
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  const query = useList<Entry>(definition.path, {
    q,
    archived,
    limit: 20,
    offset: page * 20,
  });
  async function archiveEntry() {
    if (!archive) return;
    setPending(true);
    setError('');
    try {
      await request(
        `${definition.path}/${archive.id}/${archive.archived_at ? 'restore' : 'archive'}`,
        { method: 'POST', body: { version: archive.version } },
      );
      setArchive(undefined);
      await client.invalidateQueries({ queryKey: ['warehouse'] });
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setPending(false);
    }
  }
  return (
    <section className="min-w-0 rounded-xl border border-border bg-white">
      <div className="flex flex-wrap items-end gap-3 border-b border-border p-5">
        <h2 className="mr-auto text-lg font-semibold">{definition.title}</h2>
        {manage && (
          <Button onClick={() => setEdit(null)}>Добавить запись</Button>
        )}
        <div className="basis-full" />
        <Field label="Поиск в справочнике">
          {(id) => (
            <Input
              id={id}
              value={q}
              maxLength={100}
              onChange={(e) => {
                setQ(e.target.value);
                setPage(0);
              }}
            />
          )}
        </Field>
        <Field label="Статус записей">
          {(id) => (
            <Select
              id={id}
              value={archived}
              onChange={(e) => {
                setArchived(e.target.value);
                setPage(0);
              }}
            >
              <option value="false">Активные</option>
              <option value="true">Архивные</option>
              <option value="all">Все</option>
            </Select>
          )}
        </Field>
      </div>
      {query.isPending ? (
        <LoadingState />
      ) : query.error ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : !query.data.items.length ? (
        <EmptyState
          title="Записей пока нет"
          description="Добавьте запись или измените фильтр."
        />
      ) : (
        <ul className="divide-y divide-border">
          {query.data.items.map((entry) => (
            <li
              key={entry.id}
              className="flex flex-wrap items-center gap-3 p-5"
            >
              <div className="min-w-0 flex-1 basis-40 break-words text-sm">
                <p className="font-medium">
                  {String(entry.full_name ?? entry.name ?? entry.model)}
                </p>
                <p className="mt-1 text-muted">
                  {[
                    entry.code,
                    entry.personnel_number,
                    entry.manufacturer_name,
                    entry.department_name,
                  ]
                    .filter(Boolean)
                    .join(' · ')}
                </p>
                {entry.archived_at && (
                  <StatusBadge active={false}>Архив</StatusBadge>
                )}
              </div>
              {manage && (
                <>
                  <Button variant="outline" onClick={() => setEdit(entry)}>
                    Изменить
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => {
                      setError('');
                      setArchive(entry);
                    }}
                  >
                    {entry.archived_at ? 'Восстановить' : 'Архивировать'}
                  </Button>
                </>
              )}
            </li>
          ))}
        </ul>
      )}
      <Pagination
        page={page}
        total={query.data?.total ?? 0}
        onChange={setPage}
      />
      {edit !== undefined && (
        <EntryForm
          definition={definition}
          entry={edit}
          onClose={() => setEdit(undefined)}
        />
      )}
      <ConfirmDialog
        open={!!archive}
        title={
          archive?.archived_at ? 'Восстановить запись' : 'Архивировать запись'
        }
        description="История использования записи будет сохранена."
        onClose={() => setArchive(undefined)}
        pending={pending}
      >
        <div className="space-y-4">
          {error && <Notice>{error}</Notice>}
          <Button disabled={pending} onClick={() => void archiveEntry()}>
            Подтвердить
          </Button>
        </div>
      </ConfirmDialog>
    </section>
  );
}
function EntryForm({
  definition,
  entry,
  onClose,
}: {
  definition: Definition;
  entry: Entry | null;
  onClose: () => void;
}) {
  const client = useQueryClient();
  const [values, setValues] = useState<Record<string, string>>(
    Object.fromEntries(
      definition.fields.map((field) => [
        field.key,
        String(entry?.[field.key] ?? ''),
      ]),
    ),
  );
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const manufacturers = useOptions<Manufacturer>('/inventory/manufacturers');
  const departments = useOptions<Department>('/directory/departments');
  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError('');
    const body = Object.fromEntries(
      Object.entries(values).filter(
        ([key]) =>
          !entry ||
          !definition.fields.find((field) => field.key === key)?.immutable,
      ),
    );
    try {
      await request(`${definition.path}${entry ? `/${entry.id}` : ''}`, {
        method: entry ? 'PATCH' : 'POST',
        body: { ...body, ...(entry ? { version: entry.version } : {}) },
      });
      await client.invalidateQueries({ queryKey: ['warehouse'] });
      onClose();
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setPending(false);
    }
  }
  return (
    <ConfirmDialog
      open
      title={entry ? 'Изменить запись' : 'Добавить запись'}
      description={definition.title}
      onClose={onClose}
      pending={pending}
    >
      <form className="space-y-4" onSubmit={submit}>
        {error && <Notice>{error}</Notice>}
        {definition.fields.map((field) => {
          const options =
            field.options === 'manufacturers' ? manufacturers : departments;
          return (
            <Field key={field.key} label={field.label}>
              {(id) =>
                field.options ? (
                  <>
                    <Select
                      id={id}
                      required
                      disabled={pending || !options.data}
                      value={values[field.key]}
                      onChange={(e) =>
                        setValues({ ...values, [field.key]: e.target.value })
                      }
                    >
                      <option value="">Выберите запись</option>
                      {entry &&
                        values[field.key] &&
                        !options.data?.some(
                          (option) => option.id === values[field.key],
                        ) && (
                          <option value={values[field.key]}>
                            {String(
                              entry[
                                field.options === 'manufacturers'
                                  ? 'manufacturer_name'
                                  : 'department_name'
                              ],
                            )}{' '}
                            (архив)
                          </option>
                        )}
                      {options.data?.map((option) => (
                        <option key={option.id} value={option.id}>
                          {option.name}
                        </option>
                      ))}
                    </Select>
                    {options.error && (
                      <ErrorState
                        error={options.error}
                        onRetry={() => void options.refetch()}
                      />
                    )}
                  </>
                ) : (
                  <Input
                    id={id}
                    required
                    maxLength={field.max}
                    disabled={pending || (!!entry && field.immutable)}
                    value={values[field.key]}
                    onChange={(e) =>
                      setValues({ ...values, [field.key]: e.target.value })
                    }
                  />
                )
              }
            </Field>
          );
        })}
        <Button type="submit" disabled={pending}>
          Сохранить запись
        </Button>
      </form>
    </ConfirmDialog>
  );
}
