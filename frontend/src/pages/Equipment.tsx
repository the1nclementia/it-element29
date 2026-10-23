import { useEffect, useState } from 'react';
import { Search, Table2, LayoutGrid, Wrench } from 'lucide-react';
import {
  PageHeader,
  EmptyState,
  ErrorState,
  LoadingState,
  StatusBadge,
} from '../components/common';
import { Input, Select } from '../components/ui/input';
import { useList } from '../features/inventory/api';
import type { EquipmentInstance } from '../features/inventory/types';

type ViewMode = 'table' | 'cards';

export function Equipment() {
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('active');
  const [view, setView] = useState<ViewMode>(() =>
    localStorage.getItem('equipment-view') === 'cards' ? 'cards' : 'table',
  );
  useEffect(() => localStorage.setItem('equipment-view', view), [view]);
  const instances = useList<EquipmentInstance>('/equipment/instances', {
    q,
    archived: status === 'archived' ? 'true' : 'false',
    limit: 100,
  });
  const rows = instances.data?.items ?? [];
  return (
    <>
      <PageHeader
        title="Оборудование"
        description="Физические экземпляры техники и их текущее положение"
      >
        <div
          className="flex items-center gap-1 rounded-xl border border-border bg-white p-1"
          aria-label="Вид списка"
        >
          <button
            type="button"
            className={`rounded-lg p-2 ${view === 'table' ? 'bg-primary-light text-primary' : 'text-muted'}`}
            aria-label="Таблица"
            onClick={() => setView('table')}
          >
            <Table2 className="size-4" />
          </button>
          <button
            type="button"
            className={`rounded-lg p-2 ${view === 'cards' ? 'bg-primary-light text-primary' : 'text-muted'}`}
            aria-label="Карточки"
            onClick={() => setView('cards')}
          >
            <LayoutGrid className="size-4" />
          </button>
        </div>
      </PageHeader>
      <section className="surface-card overflow-hidden">
        <div className="grid gap-3 border-b border-border p-5 sm:grid-cols-[1fr_220px]">
          <label className="relative block">
            <span className="sr-only">Поиск экземпляров</span>
            <Search className="pointer-events-none absolute left-3 top-3 size-4 text-muted" />
            <Input
              className="pl-9"
              placeholder="Серийный, инвентарный номер или получатель"
              value={q}
              maxLength={100}
              onChange={(event) => setQ(event.target.value)}
            />
          </label>
          <Select
            aria-label="Статус"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="active">Активные</option>
            <option value="archived">Архивные</option>
          </Select>
        </div>
        {instances.isPending ? (
          <LoadingState />
        ) : instances.error ? (
          <ErrorState
            error={instances.error}
            onRetry={() => void instances.refetch()}
          />
        ) : !rows.length ? (
          <EmptyState
            icon={Wrench}
            title="Экземпляры не найдены"
            description="Зарегистрированные устройства появятся здесь."
          />
        ) : view === 'table' ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-background text-xs text-muted">
                <tr>
                  <th className="px-5 py-3 font-medium">Модель</th>
                  <th className="px-5 py-3 font-medium">Серийный номер</th>
                  <th className="px-5 py-3 font-medium">Инвентарный номер</th>
                  <th className="px-5 py-3 font-medium">Положение</th>
                  <th className="px-5 py-3 font-medium">Статус</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {rows.map((row) => (
                  <tr key={row.id}>
                    <td className="px-5 py-4">
                      <p className="font-medium">
                        {row.manufacturer_name} {row.model}
                      </p>
                      <p className="mt-1 text-xs text-muted">
                        {row.internal_code}
                      </p>
                      {row.identification_warning && (
                        <p className="mt-2 text-xs text-orange-700">
                          {row.identification_warning}
                        </p>
                      )}
                    </td>
                    <td className="px-5 py-4">{row.serial_number ?? '—'}</td>
                    <td className="px-5 py-4">{row.inventory_number ?? '—'}</td>
                    <td className="px-5 py-4">
                      {row.current_recipient ??
                        row.current_building ??
                        'На складе'}
                    </td>
                    <td className="px-5 py-4">
                      <StatusBadge active={row.is_under_repair ? false : true}>
                        {row.is_under_repair
                          ? 'Ремонт'
                          : row.current_recipient
                            ? 'Выдано'
                            : 'На складе'}
                      </StatusBadge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="grid gap-4 p-5 sm:grid-cols-2 xl:grid-cols-3">
            {rows.map((row) => (
              <article
                key={row.id}
                className="rounded-xl border border-border p-5"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h2 className="font-semibold">
                      {row.manufacturer_name} {row.model}
                    </h2>
                    <p className="mt-1 text-xs text-muted">
                      {row.internal_code}
                    </p>
                    {row.identification_warning && (
                      <p className="mt-2 text-xs text-orange-700">
                        {row.identification_warning}
                      </p>
                    )}
                  </div>
                  <StatusBadge active={!row.is_under_repair}>
                    {row.is_under_repair
                      ? 'Ремонт'
                      : row.current_recipient
                        ? 'Выдано'
                        : 'На складе'}
                  </StatusBadge>
                </div>
                <dl className="mt-5 space-y-2 text-sm">
                  <div className="flex justify-between gap-3">
                    <dt className="text-muted">Серийный</dt>
                    <dd>{row.serial_number ?? '—'}</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-muted">Инвентарный</dt>
                    <dd>{row.inventory_number ?? '—'}</dd>
                  </div>
                  <div className="flex justify-between gap-3">
                    <dt className="text-muted">Положение</dt>
                    <dd>
                      {row.current_recipient ??
                        row.current_building ??
                        'На складе'}
                    </dd>
                  </div>
                </dl>
              </article>
            ))}
          </div>
        )}
      </section>
    </>
  );
}
