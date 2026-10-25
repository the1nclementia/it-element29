import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '../auth';
import {
  PageHeader,
  LoadingState,
  ErrorState,
  Notice,
  ConfirmDialog,
  EmptyState,
  StatusBadge,
} from '../components/common';
import { Button } from '../components/ui/button';
import { request } from '../lib/api';
import { ItemForm } from '../features/inventory/ItemForm';
import { Photos } from '../features/inventory/Photos';
import { useList, useOptions } from '../features/inventory/api';
import { Pagination } from '../features/inventory/shared';
import { useDraft } from '../features/issues/state';
import {
  documentNames,
  type InventoryItem,
  type PrinterModel,
  type Movement,
} from '../features/inventory/types';
export function ItemDetails() {
  const { id } = useParams();
  const { user } = useAuth();
  const client = useQueryClient();
  const basket = useDraft('issue');
  const [edit, setEdit] = useState(false);
  const [archive, setArchive] = useState(false);
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState<string[] | null>(null);
  const [added, setAdded] = useState(false);
  const query = useQuery({
    queryKey: ['warehouse', 'item', id],
    queryFn: ({ signal }) =>
      request<InventoryItem>(`/inventory/items/${id}`, { signal }),
  });
  const compatibility = useList<PrinterModel>(
    `/inventory/items/${id}/compatibilities`,
    { limit: 100 },
  );
  const printers = useOptions<PrinterModel>('/inventory/printer-models');
  const movements = useList<Movement>(`/inventory/items/${id}/movements`, {
    limit: 20,
    offset: page * 20,
  });
  const manage = !!user?.permissions.includes('inventory.manage');
  async function mutate(path: string, body: object, method = 'POST') {
    setPending(true);
    setError('');
    try {
      await request(`/inventory/items/${id}${path}`, { method, body });
      setArchive(false);
      setSelected(null);
      await client.invalidateQueries({ queryKey: ['warehouse'] });
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setPending(false);
    }
  }
  if (query.isPending) return <LoadingState />;
  if (query.error)
    return (
      <ErrorState error={query.error} onRetry={() => void query.refetch()} />
    );
  const item = query.data;
  return (
    <>
      <PageHeader
        title={item.model}
        description={`${item.internal_code} · ${item.manufacturer_name}`}
      >
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" asChild>
            <Link to="/inventory">К каталогу</Link>
          </Button>
          {manage && (
            <>
              <Button variant="outline" onClick={() => setEdit(true)}>
                Редактировать
              </Button>
              <Button variant="outline" onClick={() => setArchive(true)}>
                {item.archived_at ? 'Восстановить' : 'Архивировать'}
              </Button>
            </>
          )}
          {user?.permissions.includes('inventory.issue') &&
            !item.archived_at && (
              <Button
                disabled={basket.locked}
                onClick={() => {
                  basket.add(item);
                  setAdded(true);
                }}
              >
                В корзину
              </Button>
            )}
        </div>
      </PageHeader>
      <div className="space-y-5">
        {error && <Notice>{error}</Notice>}
        {added && (
          <Notice success>
            Позиция добавлена в корзину.{' '}
            <Link className="underline" to="/issues">
              Перейти к выдаче
            </Link>
          </Notice>
        )}
        <section className="space-y-3 rounded-xl border border-border bg-white p-5">
          <div className="flex flex-wrap items-center gap-3">
            <span className="text-2xl font-semibold">{item.balance} шт.</span>
            <StatusBadge active={!item.archived_at}>
              {item.archived_at ? 'Архив' : 'Активная позиция'}
            </StatusBadge>
            {item.is_low_stock && (
              <span className="text-sm text-orange-700">
                {item.balance === 0
                  ? 'Нет в наличии'
                  : 'Достигнут минимальный остаток — требуется пополнение'}
              </span>
            )}
          </div>
          <p className="text-sm">
            Категория: {item.category_name} · Минимум: {item.min_stock} шт.
          </p>
          {item.article && (
            <p className="break-words text-sm">Артикул: {item.article}</p>
          )}
          <p className="whitespace-pre-wrap break-words text-sm text-muted">
            {item.description}
          </p>
        </section>
        <Photos itemId={item.id} manage={manage && !item.archived_at} />
        <section className="space-y-4 rounded-xl border border-border bg-white p-5">
          <h2 className="text-lg font-semibold">Совместимость с принтерами</h2>
          {compatibility.isPending ? (
            <LoadingState />
          ) : compatibility.error ? (
            <ErrorState
              error={compatibility.error}
              onRetry={() => void compatibility.refetch()}
            />
          ) : (
            <>
              <ul className="space-y-2 text-sm">
                {compatibility.data.items.map((printer) => (
                  <li className="break-words" key={printer.id}>
                    {printer.manufacturer_name} {printer.model}
                    {printer.archived_at ? ' (архив)' : ''}
                  </li>
                ))}
              </ul>
              {!compatibility.data.items.length && (
                <p className="text-sm text-muted">
                  Совместимые модели не указаны.
                </p>
              )}
              {manage && !item.archived_at && (
                <Button
                  variant="outline"
                  onClick={() =>
                    setSelected(
                      compatibility.data.items.map((printer) => printer.id),
                    )
                  }
                >
                  Изменить совместимость
                </Button>
              )}
            </>
          )}
        </section>
        <section className="rounded-xl border border-border bg-white">
          <h2 className="p-5 text-lg font-semibold">Движения</h2>
          {movements.isPending ? (
            <LoadingState />
          ) : movements.error ? (
            <ErrorState
              error={movements.error}
              onRetry={() => void movements.refetch()}
            />
          ) : !movements.data.items.length ? (
            <EmptyState
              title="Движений пока нет"
              description="Остаток появится после проведения поступления."
            />
          ) : (
            <ul className="divide-y divide-border">
              {movements.data.items.map((movement) => (
                <li
                  key={movement.id}
                  className="flex flex-wrap justify-between gap-3 p-5 text-sm"
                >
                  <div>
                    <Link
                      className="text-primary hover:underline"
                      to={`/inventory/documents/${movement.document_id}`}
                    >
                      {movement.document_number}
                    </Link>
                    <p className="text-xs text-muted">
                      {documentNames[movement.document_type]} ·{' '}
                      {new Date(movement.occurred_at).toLocaleString('ru-RU')}
                    </p>
                  </div>
                  <span>
                    {movement.delta > 0 ? '+' : ''}
                    {movement.delta} шт.
                  </span>
                </li>
              ))}
            </ul>
          )}
          <Pagination
            page={page}
            total={movements.data?.total ?? 0}
            onChange={setPage}
          />
        </section>
      </div>
      {edit && (
        <ItemForm
          item={item}
          onClose={() => setEdit(false)}
          onSaved={() => setEdit(false)}
        />
      )}
      <ConfirmDialog
        open={archive}
        title={
          item.archived_at ? 'Восстановить позицию' : 'Архивировать позицию'
        }
        description="Архивирование возможно при нулевом остатке. Все документы и движения сохранятся."
        onClose={() => setArchive(false)}
        pending={pending}
      >
        <div className="space-y-4">
          {error && <Notice>{error}</Notice>}
          <Button
            disabled={pending}
            onClick={() =>
              void mutate(item.archived_at ? '/restore' : '/archive', {
                version: item.version,
              })
            }
          >
            Подтвердить
          </Button>
        </div>
      </ConfirmDialog>
      <ConfirmDialog
        open={selected !== null}
        title="Изменить совместимость"
        description="Выберите до 100 моделей принтеров. Производитель расходника может отличаться от производителя принтера."
        onClose={() => setSelected(null)}
        pending={pending}
      >
        <div className="space-y-4">
          {error && <Notice>{error}</Notice>}
          {printers.error ? (
            <ErrorState
              error={printers.error}
              onRetry={() => void printers.refetch()}
            />
          ) : printers.isPending ? (
            <LoadingState />
          ) : (
            <div className="max-h-80 space-y-3 overflow-y-auto">
              {[
                ...printers.data,
                ...(compatibility.data?.items.filter(
                  (printer) =>
                    printer.archived_at &&
                    !printers.data.some((active) => active.id === printer.id),
                ) ?? []),
              ].map((printer) => (
                <label key={printer.id} className="flex gap-3 text-sm">
                  <input
                    type="checkbox"
                    disabled={
                      pending ||
                      (!!printer.archived_at && !selected?.includes(printer.id))
                    }
                    checked={selected?.includes(printer.id) ?? false}
                    onChange={(event) =>
                      setSelected((previous) =>
                        event.target.checked
                          ? [...(previous ?? []), printer.id]
                          : (previous ?? []).filter(
                              (value) => value !== printer.id,
                            ),
                      )
                    }
                  />
                  <span className="break-words">
                    {printer.manufacturer_name} {printer.model}
                    {printer.archived_at
                      ? ' (архив — снимите выбор для сохранения)'
                      : ''}
                  </span>
                </label>
              ))}
            </div>
          )}
          <Button
            disabled={
              pending || !printers.data || (selected?.length ?? 0) > 100
            }
            onClick={() =>
              void mutate(
                '/compatibilities',
                { version: item.version, printer_model_ids: selected },
                'PUT',
              )
            }
          >
            Сохранить совместимость
          </Button>
        </div>
      </ConfirmDialog>
    </>
  );
}
