import { useMemo, useState } from 'react';
import { ArrowLeftRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import {
  PageHeader,
  EmptyState,
  ErrorState,
  LoadingState,
} from '../components/common';
import { Input } from '../components/ui/input';
import { Button } from '../components/ui/button';
import { useList } from '../features/inventory/api';
import { request } from '../lib/api';
import type { EquipmentInstance } from '../features/inventory/types';

type Destination = {
  building: string;
  room: string;
  department: string;
  recipient: string;
};

export function Movements() {
  const instances = useList<EquipmentInstance>('/equipment/instances', {
    limit: 100,
  });
  const history = useList<Record<string, unknown>>('/equipment/movements', {
    limit: 20,
  });
  const [selected, setSelected] = useState<string[]>([]);
  const [destination, setDestination] = useState<Destination>({
    building: '',
    room: '',
    department: '',
    recipient: '',
  });
  const [error, setError] = useState<Error>();
  const [saving, setSaving] = useState(false);
  const rows = instances.data?.items ?? [];
  const selectedRows = useMemo(
    () => rows.filter((row) => selected.includes(row.id)),
    [rows, selected],
  );
  const update = (field: keyof Destination, value: string) =>
    setDestination((current) => ({ ...current, [field]: value }));
  const submit = async () => {
    setSaving(true);
    setError(undefined);
    try {
      await request('/equipment/movements', {
        method: 'POST',
        headers: { 'Idempotency-Key': crypto.randomUUID() },
        body: {
          document_date: new Date().toISOString().slice(0, 10),
          destination_building: destination.building || null,
          destination_room: destination.room || null,
          destination_department: destination.department || null,
          destination_recipient: destination.recipient || null,
          items: selectedRows.map((row) => ({
            equipment_instance_id: row.id,
            version: row.version,
            current_building: row.current_building,
            current_room: row.current_room,
            current_department: row.current_department,
            current_recipient: row.current_recipient,
          })),
        },
      });
      setSelected([]);
      await Promise.all([instances.refetch(), history.refetch()]);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught
          : new Error('Не удалось выполнить перемещение.'),
      );
    } finally {
      setSaving(false);
    }
  };
  return (
    <>
      <PageHeader
        title="Перемещения"
        description="Перемещение оборудования между подразделениями и кабинетами"
      />
      <section className="grid gap-5 xl:grid-cols-[1.2fr_0.8fr]">
        <div className="surface-card overflow-hidden">
          {instances.isPending ? (
            <LoadingState />
          ) : instances.error ? (
            <ErrorState
              error={instances.error}
              onRetry={() => void instances.refetch()}
            />
          ) : !rows.length ? (
            <EmptyState
              icon={ArrowLeftRight}
              title="Нет доступных экземпляров"
              description="Зарегистрированные устройства появятся в реестре оборудования."
            >
              <Button variant="outline" asChild>
                <Link to="/equipment">Открыть оборудование</Link>
              </Button>
            </EmptyState>
          ) : (
            <>
              <div className="border-b border-border p-5">
                <h2 className="font-semibold">Выберите устройства</h2>
                <p className="mt-1 text-sm text-muted">
                  В ремонтных и складских экземплярах перемещение недоступно.
                </p>
              </div>
              <div className="divide-y divide-border">
                {rows.map((row) => (
                  <label
                    key={row.id}
                    className="flex cursor-pointer gap-3 p-4 text-sm"
                  >
                    <input
                      type="checkbox"
                      checked={selected.includes(row.id)}
                      disabled={
                        row.is_under_repair ||
                        (!row.current_building &&
                          !row.current_room &&
                          !row.current_department &&
                          !row.current_recipient)
                      }
                      onChange={(event) =>
                        setSelected((current) =>
                          event.target.checked
                            ? [...current, row.id]
                            : current.filter((id) => id !== row.id),
                        )
                      }
                    />
                    <span>
                      <span className="block font-medium">
                        {row.manufacturer_name} {row.model}
                      </span>
                      <span className="text-muted">
                        {row.serial_number ?? 'Без серийного номера'} ·{' '}
                        {row.current_recipient ??
                          row.current_building ??
                          'На складе'}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
            </>
          )}
        </div>
        <div className="surface-card p-5">
          <h2 className="font-semibold">Пункт назначения</h2>
          <div className="mt-4 grid gap-3">
            <Input
              aria-label="Здание назначения"
              placeholder="Здание"
              value={destination.building}
              onChange={(e) => update('building', e.target.value)}
            />
            <Input
              aria-label="Кабинет назначения"
              placeholder="Кабинет"
              value={destination.room}
              onChange={(e) => update('room', e.target.value)}
            />
            <Input
              aria-label="Подразделение назначения"
              placeholder="Подразделение"
              value={destination.department}
              onChange={(e) => update('department', e.target.value)}
            />
            <Input
              aria-label="Ответственный назначения"
              placeholder="Ответственный"
              value={destination.recipient}
              onChange={(e) => update('recipient', e.target.value)}
            />
            {error && (
              <p role="alert" className="text-sm text-red-700">
                {error.message}
              </p>
            )}
            <Button
              disabled={
                !selectedRows.length ||
                !Object.values(destination).some(Boolean) ||
                saving
              }
              onClick={() => void submit()}
            >
              {saving ? 'Сохраняем…' : `Переместить (${selectedRows.length})`}
            </Button>
          </div>
        </div>
      </section>
      <section className="surface-card mt-5 overflow-hidden">
        <div className="border-b border-border p-5">
          <h2 className="font-semibold">История перемещений</h2>
        </div>
        {history.isPending ? (
          <LoadingState />
        ) : history.error ? (
          <ErrorState
            error={history.error}
            onRetry={() => void history.refetch()}
          />
        ) : !history.data?.items.length ? (
          <EmptyState
            title="Перемещений пока нет"
            description="История появится после проведения первой операции."
          />
        ) : (
          <div className="divide-y divide-border">
            {history.data.items.map((item) => {
              const before = item.before as Record<string, string | null>;
              const after = item.after as Record<string, string | null>;
              return (
                <article key={String(item.id)} className="p-4 text-sm">
                  <p className="font-medium">Перемещение оборудования</p>
                  <p className="mt-1 text-muted">
                    {before.building ?? 'Без здания'} /{' '}
                    {before.room ?? 'без кабинета'} →{' '}
                    {after.building ?? 'Без здания'} /{' '}
                    {after.room ?? 'без кабинета'}
                  </p>
                  <p className="mt-1 text-xs text-muted">
                    Ответственный: {after.recipient ?? 'не указан'}
                  </p>
                </article>
              );
            })}
          </div>
        )}
      </section>
    </>
  );
}
