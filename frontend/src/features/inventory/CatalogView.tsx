import { Grid2X2, ImageOff, List, Table2 } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import { StatusBadge } from '../../components/common';
import { Button } from '../../components/ui/button';
import { sameOriginPhoto } from './api';
import type { InventoryItem } from './types';

export type CatalogViewMode = 'cards' | 'list' | 'table';

const modes = [
  { value: 'cards', label: 'Плитка', Icon: Grid2X2 },
  { value: 'list', label: 'Компактный список', Icon: List },
  { value: 'table', label: 'Таблица', Icon: Table2 },
] as const;

export function CatalogViewSwitcher({
  value,
  onChange,
}: {
  value: CatalogViewMode;
  onChange: (value: CatalogViewMode) => void;
}) {
  return (
    <div
      className="flex flex-wrap items-center gap-1 rounded-xl border border-border bg-slate-50 p-1"
      aria-label="Режим отображения каталога"
    >
      {modes.map(({ value: mode, label, Icon }) => (
        <Button
          key={mode}
          type="button"
          size="sm"
          variant={value === mode ? 'default' : 'ghost'}
          aria-pressed={value === mode}
          aria-label={label}
          title={label}
          onClick={() => onChange(mode)}
        >
          <Icon aria-hidden="true" />
          <span className="sr-only sm:not-sr-only">{label}</span>
        </Button>
      ))}
    </div>
  );
}

function StockMessage({ item }: { item: InventoryItem }) {
  if (!item.is_low_stock) return null;
  return (
    <p className="text-xs text-orange-700">
      {item.balance === 0
        ? 'Нет в наличии'
        : `Минимум ${item.min_stock} — требуется пополнение`}
    </p>
  );
}

function ItemPhoto({
  item,
  large = false,
}: {
  item: InventoryItem;
  large?: boolean;
}) {
  const photo = sameOriginPhoto(item.primary_photo_url);
  return photo ? (
    <img
      className={`${large ? 'h-44 w-full bg-white p-3' : 'size-16'} shrink-0 rounded-lg border border-border object-contain`}
      src={photo}
      alt={`Фото ${item.model}`}
    />
  ) : (
    <div
      className={`${large ? 'h-44 w-full' : 'size-16'} flex shrink-0 items-center justify-center rounded-lg border border-dashed border-border bg-slate-50 text-slate-400`}
      aria-label="Фото отсутствует"
    >
      <ImageOff aria-hidden="true" className={large ? 'size-10' : 'size-6'} />
    </div>
  );
}

function AddButton({
  item,
  onAdd,
  disabled,
}: {
  item: InventoryItem;
  onAdd?: (item: InventoryItem) => void;
  disabled: boolean;
}) {
  if (!onAdd || item.archived_at) return null;
  return (
    <Button
      type="button"
      variant="outline"
      disabled={disabled}
      aria-label={`Добавить в корзину ${item.internal_code}`}
      onClick={() => onAdd(item)}
    >
      Добавить
    </Button>
  );
}

function ItemMeta({ item }: { item: InventoryItem }) {
  return (
    <>
      <p className="text-xs text-muted">
        {item.internal_code} · {item.manufacturer_name} · {item.category_name}
      </p>
      {item.article && (
        <p className="text-xs text-muted">Артикул: {item.article}</p>
      )}
      {item.archived_at && <StatusBadge active={false}>Архив</StatusBadge>}
    </>
  );
}

function ItemTitle({ item }: { item: InventoryItem }) {
  return (
    <Link
      className="line-clamp-3 break-words font-semibold text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
      title={item.model}
      to={`/inventory/items/${item.id}`}
    >
      {item.model}
    </Link>
  );
}

export function CatalogItemsView({
  items,
  mode,
  onAdd,
  disabled = false,
}: {
  items: InventoryItem[];
  mode: CatalogViewMode;
  onAdd?: (item: InventoryItem) => void;
  disabled?: boolean;
}) {
  const navigate = useNavigate();
  const openCard = (event: React.MouseEvent<HTMLLIElement>) => {
    if ((event.target as HTMLElement).closest('a,button')) return;
    navigate(
      `/inventory/items/${(event.currentTarget as HTMLLIElement).dataset.itemId}`,
    );
  };
  const openCardWithKeyboard = (event: React.KeyboardEvent<HTMLLIElement>) => {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      navigate(
        `/inventory/items/${(event.currentTarget as HTMLLIElement).dataset.itemId}`,
      );
    }
  };
  if (mode === 'cards') {
    return (
      <ul className="grid gap-4 p-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        {items.map((item) => (
          <li
            key={item.id}
            data-item-id={item.id}
            role="link"
            tabIndex={0}
            onClick={openCard}
            onKeyDown={openCardWithKeyboard}
            className="flex min-w-0 flex-col gap-3 rounded-xl border border-border bg-white p-4 shadow-xs transition-shadow hover:shadow-md"
          >
            <Link
              to={`/inventory/items/${item.id}`}
              aria-label={`Открыть ${item.model}`}
            >
              <ItemPhoto item={item} large />
            </Link>
            <div className="min-w-0 space-y-1">
              <ItemTitle item={item} />
              <ItemMeta item={item} />
            </div>
            <div className="mt-auto flex items-end justify-between gap-3">
              <div>
                <p
                  className="font-semibold"
                  aria-label={`Остаток ${item.internal_code}`}
                >
                  {item.balance} {item.unit === 'pcs' ? 'шт.' : item.unit}
                </p>
                <StockMessage item={item} />
              </div>
              <AddButton item={item} onAdd={onAdd} disabled={disabled} />
            </div>
          </li>
        ))}
      </ul>
    );
  }

  if (mode === 'table') {
    return (
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead>
            <tr className="border-b border-border bg-slate-50/70">
              {[
                'Название',
                'Код',
                'Производитель',
                'Категория',
                'Остаток',
                'Минимум',
                'Действие',
              ].map((label) => (
                <th
                  key={label}
                  className="px-4 py-3 text-xs font-medium text-muted"
                  scope="col"
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr
                key={item.id}
                className="border-b border-border last:border-b-0 hover:bg-slate-50/60"
              >
                <td className="max-w-64 px-4 py-4">
                  <ItemTitle item={item} />
                </td>
                <td className="px-4 py-4">{item.internal_code}</td>
                <td className="px-4 py-4">{item.manufacturer_name}</td>
                <td className="px-4 py-4">{item.category_name}</td>
                <td className="px-4 py-4">
                  <span className="font-semibold">
                    {item.balance} {item.unit === 'pcs' ? 'шт.' : item.unit}
                  </span>
                  <StockMessage item={item} />
                </td>
                <td className="px-4 py-4">{item.min_stock}</td>
                <td className="px-4 py-4">
                  <AddButton item={item} onAdd={onAdd} disabled={disabled} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <ul className="divide-y divide-border">
      {items.map((item) => (
        <li key={item.id} className="flex flex-wrap items-center gap-4 p-5">
          <Link
            to={`/inventory/items/${item.id}`}
            aria-label={`Открыть ${item.model}`}
          >
            <ItemPhoto item={item} />
          </Link>
          <div className="min-w-0 flex-1 basis-40">
            <ItemTitle item={item} />
            <ItemMeta item={item} />
          </div>
          <div className="text-sm">
            <p
              className="font-semibold"
              aria-label={`Остаток ${item.internal_code}`}
            >
              {item.balance} {item.unit === 'pcs' ? 'шт.' : item.unit}
            </p>
            <StockMessage item={item} />
          </div>
          <AddButton item={item} onAdd={onAdd} disabled={disabled} />
        </li>
      ))}
    </ul>
  );
}
