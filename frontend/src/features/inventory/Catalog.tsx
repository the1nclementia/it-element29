import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ExportButton } from './ExportButton';
import {
  EmptyState,
  ErrorState,
  LoadingState,
  Field,
} from '../../components/common';
import { Input, Select } from '../../components/ui/input';
import { Button } from '../../components/ui/button';
import { useList, useOptions } from './api';
import { Pagination } from './shared';
import {
  CatalogItemsView,
  CatalogViewSwitcher,
  type CatalogViewMode,
} from './CatalogView';
import type {
  InventoryItem,
  Manufacturer,
  Category,
  PrinterModel,
} from './types';

const VIEW_KEY = 'warehouse.catalog.view';
function readViewMode(): CatalogViewMode {
  const value = window.localStorage.getItem(VIEW_KEY);
  return value === 'list' || value === 'table' || value === 'cards'
    ? value
    : 'cards';
}

export function Catalog({
  onAdd,
  disabled = false,
  compact = false,
  basketCount,
}: {
  onAdd?: (item: InventoryItem) => void;
  disabled?: boolean;
  compact?: boolean;
  basketCount?: number;
}) {
  const [parameters] = useSearchParams();
  const [viewMode, setViewMode] = useState<CatalogViewMode>(readViewMode);
  const [q, setQ] = useState('');
  const [page, setPage] = useState(0);
  const [filters, setFilters] = useState<Record<string, string>>(
    !compact && parameters.get('low_stock') === 'true'
      ? { low_stock: 'true' }
      : {},
  );
  const items = useList<InventoryItem>('/inventory/items', {
    q,
    offset: page * 20,
    limit: 20,
    ...filters,
    ...(compact ? { archived: 'false' } : {}),
  });
  const categories = useOptions<Category>('/inventory/categories');
  const manufacturers = useOptions<Manufacturer>('/inventory/manufacturers');
  const printers = useOptions<PrinterModel>('/inventory/printer-models');
  useEffect(() => {
    if (!compact) window.localStorage.setItem(VIEW_KEY, viewMode);
  }, [compact, viewMode]);
  const filter = (name: string, value: string) => {
    setFilters((previous) => ({ ...previous, [name]: value }));
    setPage(0);
  };
  return (
    <section className="min-w-0 rounded-xl border border-border bg-white">
      {basketCount !== undefined && (
        <div
          data-testid="catalog-sticky-actions"
          className="sticky top-0 z-20 flex justify-end border-b border-border bg-white/95 p-3 backdrop-blur"
        >
          <Button variant="outline" asChild>
            <Link to="/issues">Корзина ({basketCount})</Link>
          </Button>
        </div>
      )}
      <div className="space-y-4 border-b border-border p-5">
        <Field label="Поиск позиций">
          {(id) => (
            <Input
              id={id}
              placeholder="Код, модель или артикул"
              value={q}
              maxLength={100}
              onChange={(e) => {
                setQ(e.target.value);
                setPage(0);
              }}
            />
          )}
        </Field>
        {!compact && (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm font-medium">Позиции склада</p>
            <CatalogViewSwitcher value={viewMode} onChange={setViewMode} />
          </div>
        )}
        {!compact && (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            <Field label="Категория">
              {(id) => (
                <Select
                  id={id}
                  value={filters.category_id ?? ''}
                  onChange={(e) => filter('category_id', e.target.value)}
                >
                  <option value="">Все категории</option>
                  {categories.data?.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="Производитель">
              {(id) => (
                <Select
                  id={id}
                  value={filters.manufacturer_id ?? ''}
                  onChange={(e) => filter('manufacturer_id', e.target.value)}
                >
                  <option value="">Все производители</option>
                  {manufacturers.data?.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.name}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="Совместимый принтер">
              {(id) => (
                <Select
                  id={id}
                  value={filters.printer_model_id ?? ''}
                  onChange={(e) => filter('printer_model_id', e.target.value)}
                >
                  <option value="">Все модели</option>
                  {printers.data?.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.manufacturer_name} {item.model}
                    </option>
                  ))}
                </Select>
              )}
            </Field>
            <Field label="Наличие">
              {(id) => (
                <Select
                  id={id}
                  value={filters.in_stock ?? ''}
                  onChange={(e) => filter('in_stock', e.target.value)}
                >
                  <option value="">Любой остаток</option>
                  <option value="true">В наличии</option>
                  <option value="false">Нет в наличии</option>
                </Select>
              )}
            </Field>
            <Field label="Статус позиции">
              {(id) => (
                <Select
                  id={id}
                  value={filters.archived ?? 'false'}
                  onChange={(e) => filter('archived', e.target.value)}
                >
                  <option value="false">Активные</option>
                  <option value="true">Архивные</option>
                  <option value="all">Все</option>
                </Select>
              )}
            </Field>
            <Field label="Сортировка">
              {(id) => (
                <Select
                  id={id}
                  value={`${filters.sort ?? 'code'}:${filters.direction ?? 'asc'}`}
                  onChange={(e) => {
                    const [sort, direction] = e.target.value.split(':');
                    setFilters((previous) => ({
                      ...previous,
                      sort,
                      direction,
                    }));
                    setPage(0);
                  }}
                >
                  <option value="code:asc">Код А–Я</option>
                  <option value="code:desc">Код Я–А</option>
                  <option value="model:asc">Модель А–Я</option>
                  <option value="balance:asc">Остаток по возрастанию</option>
                  <option value="balance:desc">Остаток по убыванию</option>
                </Select>
              )}
            </Field>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={filters.low_stock === 'true'}
                onChange={(e) =>
                  filter('low_stock', e.target.checked ? 'true' : '')
                }
              />
              Требуют пополнения
            </label>
          </div>
        )}
        {!compact && (
          <ExportButton
            kind="balances"
            parameters={{ q, ...filters }}
            label="Скачать остатки в Excel"
          />
        )}
        {[categories.error, manufacturers.error, printers.error]
          .filter(Boolean)
          .slice(0, 1)
          .map((error) => (
            <ErrorState
              key="options"
              error={error!}
              onRetry={() => {
                void categories.refetch();
                void manufacturers.refetch();
                void printers.refetch();
              }}
            />
          ))}
      </div>
      {items.isPending ? (
        <LoadingState />
      ) : items.error ? (
        <ErrorState error={items.error} onRetry={() => void items.refetch()} />
      ) : !items.data.items.length ? (
        <EmptyState
          title="Позиции не найдены"
          description="Измените фильтры или добавьте первую складскую позицию."
        />
      ) : (
        <CatalogItemsView
          items={items.data.items}
          mode={compact ? 'list' : viewMode}
          onAdd={onAdd}
          disabled={disabled}
        />
      )}
      <Pagination
        page={page}
        total={items.data?.total ?? 0}
        onChange={setPage}
      />
    </section>
  );
}
