import { useRef, useState } from 'react';
import { Plus, Search } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import {
  Field,
  Notice,
  ErrorState,
  ConfirmDialog,
} from '../../components/common';
import { Button } from '../../components/ui/button';
import { Input, Select } from '../../components/ui/input';
import { request } from '../../lib/api';
import { useOptions } from './api';
import type { Manufacturer, Category } from './types';

export function ReferenceSelect({
  kind,
  value,
  initialName,
  disabled,
  onChange,
}: {
  kind: 'categories' | 'manufacturers';
  value: string;
  initialName?: string;
  disabled: boolean;
  onChange: (id: string) => void;
}) {
  const category = kind === 'categories';
  const [search, setSearch] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);
  const query = useOptions<Manufacturer | Category>(
    `/inventory/${kind}`,
    search,
  );
  const client = useQueryClient();
  const [selected, setSelected] = useState<
    { id: string; name: string } | undefined
  >(value ? { id: value, name: initialName ?? '' } : undefined);
  const [create, setCreate] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  async function save() {
    setError('');
    if (
      !name.trim() ||
      (category && !/^[a-z0-9][a-z0-9_-]*$/i.test(code.trim()))
    ) {
      setError(
        category
          ? 'Укажите название и код категории: латинские буквы, цифры, дефис или подчёркивание.'
          : 'Укажите название производителя.',
      );
      return;
    }
    setPending(true);
    try {
      const result = await request<Manufacturer | Category>(
        `/inventory/${kind}`,
        {
          method: 'POST',
          body: {
            name: name.trim(),
            ...(category ? { code: code.trim().toLowerCase() } : {}),
          },
        },
      );
      setSelected(result);
      onChange(result.id);
      setSearch('');
      setCreate(false);
      setName('');
      setCode('');
      await client.invalidateQueries({
        queryKey: ['warehouse', 'options', `/inventory/${kind}`],
      });
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setPending(false);
    }
  }
  return (
    <div className="min-w-0 space-y-2">
      <Field label={category ? 'Категория' : 'Производитель'}>
        {(id) => (
          <div className="flex items-center gap-2">
            <Select
              id={id}
              required
              disabled={disabled || pending || (query.isPending && !value)}
              value={value}
              onChange={(event) => {
                setSelected(
                  query.data?.find(
                    (option) => option.id === event.target.value,
                  ),
                );
                onChange(event.target.value);
              }}
            >
              <option value="">
                {category ? 'Выберите категорию' : 'Выберите производителя'}
              </option>
              {selected &&
                selected.id === value &&
                !query.data?.some((option) => option.id === value) && (
                  <option value={selected.id}>
                    {selected.name}
                    {!search && query.data && selected.name === initialName
                      ? ' (архив)'
                      : ''}
                  </option>
                )}
              {query.data?.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.name}
                </option>
              ))}
            </Select>
            <Button
              ref={trigger}
              type="button"
              variant="outline"
              size="sm"
              className="reference-create"
              disabled={disabled || pending}
              onClick={() => {
                setCreate(true);
                setError('');
              }}
              aria-label={category ? 'Новая категория' : 'Новый производитель'}
            >
              <Plus aria-hidden="true" />
              <span>{category ? 'Новая' : 'Новый'}</span>
            </Button>
            {!category && (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                aria-label="Открыть поиск производителя"
                aria-expanded={searchOpen}
                disabled={disabled}
                onClick={() => {
                  setSearchOpen(!searchOpen);
                  if (searchOpen) setSearch('');
                }}
              >
                <Search />
              </Button>
            )}
          </div>
        )}
      </Field>
      {!category && searchOpen && (
        <Field label="Поиск производителя">
          {(id) => (
            <Input
              id={id}
              maxLength={100}
              value={search}
              disabled={disabled || pending}
              placeholder="Введите название"
              onChange={(event) => setSearch(event.target.value)}
            />
          )}
        </Field>
      )}
      {query.isPending && (
        <p role="status" className="text-xs text-muted">
          Загружаем справочник…
        </p>
      )}
      {query.error && (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      )}
      {query.data?.length === 0 && (
        <p className="text-xs text-muted">
          {search
            ? 'По этому запросу записей нет.'
            : 'Нет активных записей. Добавьте первую.'}
        </p>
      )}
      <ConfirmDialog
        open={create}
        title={category ? 'Новая категория' : 'Новый производитель'}
        description="Запись появится в справочнике и будет выбрана в карточке товара."
        pending={pending}
        onClose={() => setCreate(false)}
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          trigger.current?.focus();
        }}
        className="z-[70] max-w-md"
      >
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            event.stopPropagation();
            void save();
          }}
        >
          {error && <Notice>{error}</Notice>}
          {category && (
            <Field
              label="Код новой категории"
              hint="Латинские буквы, цифры, дефис или подчёркивание. Код нельзя изменить."
            >
              {(id) => (
                <Input
                  id={id}
                  maxLength={50}
                  disabled={pending}
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                />
              )}
            </Field>
          )}
          <Field
            label={
              category
                ? 'Название новой категории'
                : 'Название нового производителя'
            }
          >
            {(id) => (
              <Input
                id={id}
                maxLength={200}
                disabled={pending}
                value={name}
                onChange={(event) => setName(event.target.value)}
              />
            )}
          </Field>
          <div className="flex justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={pending}
              onClick={() => setCreate(false)}
            >
              Отмена
            </Button>
            <Button type="submit" disabled={pending}>
              {pending
                ? 'Сохраняем…'
                : category
                  ? 'Сохранить категорию'
                  : 'Сохранить производителя'}
            </Button>
          </div>
        </form>
      </ConfirmDialog>
    </div>
  );
}
