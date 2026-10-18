import { Notice } from '../../components/common';
import { Button } from '../../components/ui/button';
import { ApiError } from '../../lib/api';
import type { BasketLine } from '../issues/state';
export function CommandError({
  error,
  lines = [],
}: {
  error?: Error;
  lines?: BasketLine[];
}) {
  if (!error) return null;
  return (
    <Notice>
      <div>
        {error.message}
        {error instanceof ApiError &&
          error.detail?.items?.map((item) => (
            <p key={item.inventory_item_id}>
              {lines.find((line) => line.item.id === item.inventory_item_id)
                ?.item.internal_code ?? 'Позиция'}{' '}
              · Доступно: {item.available} шт., запрошено: {item.requested} шт.
            </p>
          ))}
      </div>
    </Notice>
  );
}
export function Pagination({
  page,
  total,
  onChange,
}: {
  page: number;
  total: number;
  onChange: (page: number) => void;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border p-4 text-sm">
      <span>Всего: {total}</span>
      <div className="flex gap-2">
        <Button
          variant="outline"
          disabled={page === 0}
          onClick={() => onChange(page - 1)}
        >
          Назад
        </Button>
        <Button
          variant="outline"
          disabled={(page + 1) * 20 >= total}
          onClick={() => onChange(page + 1)}
        >
          Далее
        </Button>
      </div>
    </div>
  );
}
