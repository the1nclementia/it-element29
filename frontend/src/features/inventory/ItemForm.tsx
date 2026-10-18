import { useState, type FormEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  ConfirmDialog,
  Field,
  Notice,
  ErrorState,
} from '../../components/common';
import { Input, Select } from '../../components/ui/input';
import { Button } from '../../components/ui/button';
import { request } from '../../lib/api';
import { useOptions } from './api';
import type { InventoryItem, Manufacturer, Category } from './types';
export function ItemForm({
  item,
  onClose,
  onSaved,
}: {
  item?: InventoryItem;
  onClose: () => void;
  onSaved: (item: InventoryItem) => void;
}) {
  const client = useQueryClient();
  const [form, setForm] = useState({
    internal_code: item?.internal_code ?? '',
    category_id: item?.category_id ?? '',
    manufacturer_id: item?.manufacturer_id ?? '',
    model: item?.model ?? '',
    article: item?.article ?? '',
    description: item?.description ?? '',
    min_stock: item?.min_stock ?? 0,
  });
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  const manufacturers = useOptions<Manufacturer>('/inventory/manufacturers');
  const categories = useOptions<Category>('/inventory/categories');
  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError('');
    try {
      const { internal_code, ...fields } = form;
      const result = await request<InventoryItem>(
        item ? `/inventory/items/${item.id}` : '/inventory/items',
        {
          method: item ? 'PATCH' : 'POST',
          body: item
            ? { ...fields, version: item.version }
            : { ...fields, internal_code },
        },
      );
      await client.invalidateQueries({ queryKey: ['warehouse'] });
      onSaved(result);
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setPending(false);
    }
  }
  return (
    <ConfirmDialog
      open
      title={item ? 'Редактировать позицию' : 'Создать позицию'}
      description="Остаток изменяется только складскими документами. Код позиции после создания не меняется."
      onClose={onClose}
      pending={pending}
    >
      <form className="space-y-4" onSubmit={submit}>
        {error && <Notice>{error}</Notice>}
        {(manufacturers.error || categories.error) && (
          <ErrorState
            error={(manufacturers.error || categories.error)!}
            onRetry={() => {
              void manufacturers.refetch();
              void categories.refetch();
            }}
          />
        )}
        <Field label="Внутренний код">
          {(id) => (
            <Input
              id={id}
              required
              maxLength={50}
              disabled={pending || !!item}
              value={form.internal_code}
              onChange={(e) =>
                setForm({
                  ...form,
                  internal_code: e.target.value.toUpperCase(),
                })
              }
            />
          )}
        </Field>
        <Field label="Категория">
          {(id) => (
            <Select
              id={id}
              required
              disabled={pending}
              value={form.category_id}
              onChange={(e) =>
                setForm({ ...form, category_id: e.target.value })
              }
            >
              <option value="">Выберите категорию</option>
              {item &&
                !categories.data?.some(
                  (value) => value.id === item.category_id,
                ) && (
                  <option value={item.category_id}>
                    {item.category_name} (архив)
                  </option>
                )}
              {categories.data?.map((value) => (
                <option key={value.id} value={value.id}>
                  {value.name}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="Производитель">
          {(id) => (
            <Select
              id={id}
              required
              disabled={pending}
              value={form.manufacturer_id}
              onChange={(e) =>
                setForm({ ...form, manufacturer_id: e.target.value })
              }
            >
              <option value="">Выберите производителя</option>
              {item &&
                !manufacturers.data?.some(
                  (value) => value.id === item.manufacturer_id,
                ) && (
                  <option value={item.manufacturer_id}>
                    {item.manufacturer_name} (архив)
                  </option>
                )}
              {manufacturers.data?.map((value) => (
                <option key={value.id} value={value.id}>
                  {value.name}
                </option>
              ))}
            </Select>
          )}
        </Field>
        <Field label="Модель расходника">
          {(id) => (
            <Input
              id={id}
              required
              maxLength={200}
              disabled={pending}
              value={form.model}
              onChange={(e) => setForm({ ...form, model: e.target.value })}
            />
          )}
        </Field>
        <Field label="Артикул">
          {(id) => (
            <Input
              id={id}
              maxLength={100}
              disabled={pending}
              value={form.article}
              onChange={(e) => setForm({ ...form, article: e.target.value })}
            />
          )}
        </Field>
        <Field label="Описание">
          {(id) => (
            <textarea
              id={id}
              className="min-h-24 w-full rounded-lg border border-border p-3 text-sm"
              maxLength={5000}
              disabled={pending}
              value={form.description}
              onChange={(e) =>
                setForm({ ...form, description: e.target.value })
              }
            />
          )}
        </Field>
        <Field label="Минимальный остаток">
          {(id) => (
            <Input
              id={id}
              type="number"
              min={0}
              max={Number.MAX_SAFE_INTEGER}
              step={1}
              required
              disabled={pending}
              value={form.min_stock}
              onChange={(e) =>
                setForm({ ...form, min_stock: Number(e.target.value) })
              }
            />
          )}
        </Field>
        <Button
          type="submit"
          disabled={pending || !categories.data || !manufacturers.data}
        >
          {pending ? 'Сохраняем…' : 'Сохранить позицию'}
        </Button>
      </form>
    </ConfirmDialog>
  );
}
