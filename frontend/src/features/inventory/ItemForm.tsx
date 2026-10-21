import { useState, type FormEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  ConfirmDialog,
  Field,
  Notice,
  ErrorState,
} from '../../components/common';
import { Input } from '../../components/ui/input';
import { Button } from '../../components/ui/button';
import { request } from '../../lib/api';
import { sameOriginPhoto, useList, useOptions } from './api';
import { ReferenceSelect } from './ReferenceSelect';
import { PhotoPicker, usePhotoQueue } from './PhotoPicker';
import type { InventoryItem, Photo, PrinterModel } from './types';
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
  const [saved, setSaved] = useState<InventoryItem>();
  const queue = usePhotoQueue();
  const photos = useList<Photo>(
    `/inventory/items/${item?.id ?? saved?.id ?? 'new'}/photos`,
    {},
    !!(item || saved),
  );
  const printers = useOptions<PrinterModel>('/inventory/printer-models');
  const compatibility = useList<PrinterModel>(
    `/inventory/items/${item?.id ?? 'new'}/compatibilities`,
    { limit: 100 },
    !!item,
  );
  const [selectedPrinters, setSelectedPrinters] = useState<string[] | null>(
    null,
  );
  const [printerSearch, setPrinterSearch] = useState('');
  const [compatibilitySaved, setCompatibilitySaved] = useState(false);
  const [removedPhotos, setRemovedPhotos] = useState<string[]>([]);
  const [primaryPhoto, setPrimaryPhoto] = useState<string>();
  const selected =
    selectedPrinters ??
    compatibility.data?.items.map((printer) => printer.id) ??
    [];
  const availablePrinters = [
    ...(printers.data ?? []),
    ...(compatibility.data?.items.filter(
      (printer) =>
        printer.archived_at &&
        !printers.data?.some((active) => active.id === printer.id),
    ) ?? []),
  ];
  const filteredPrinters = availablePrinters.filter((printer) =>
    `${printer.manufacturer_name} ${printer.model}`
      .toLocaleLowerCase()
      .includes(printerSearch.toLocaleLowerCase()),
  );
  const locked = pending || !!saved;
  async function submit(event: FormEvent) {
    event.preventDefault();
    setPending(true);
    setError('');
    try {
      const { internal_code, ...fields } = form;
      let result =
        saved ??
        (await request<InventoryItem>(
          item ? `/inventory/items/${item.id}` : '/inventory/items',
          {
            method: item ? 'PATCH' : 'POST',
            body: item
              ? { ...fields, version: item.version }
              : { ...fields, internal_code },
          },
        ));
      setSaved(result);
      if (selectedPrinters !== null && !compatibilitySaved) {
        result = await request<InventoryItem>(
          `/inventory/items/${result.id}/compatibilities`,
          {
            method: 'PUT',
            body: {
              version: result.version,
              printer_model_ids: selectedPrinters,
            },
          },
        );
        setSaved(result);
        setCompatibilitySaved(true);
      }
      for (const photoId of removedPhotos) {
        await request(
          `/inventory/items/${result.id}/photos/${photoId}/archive`,
          { method: 'POST' },
        );
        setRemovedPhotos((previous) => previous.filter((id) => id !== photoId));
      }
      if (primaryPhoto) {
        await request(`/inventory/items/${result.id}/photos/${primaryPhoto}`, {
          method: 'PATCH',
          body: { is_primary: true },
        });
        setPrimaryPhoto(undefined);
      }
      await queue.upload(result.id);
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
      description="Заполните данные товара. Остаток учитывается через поступления и выдачи."
      onClose={onClose}
      pending={pending}
      className="item-form-dialog"
      bodyClassName="item-form-dialog-body"
    >
      <form className="item-form" onSubmit={submit}>
        <div className="item-form-scroll">
          {error && <Notice>{error}</Notice>}
          {saved && (
            <Notice success>
              Данные товара сохранены. Завершите сохранение фотографий и
              совместимости.
            </Notice>
          )}
          <section
            aria-labelledby="item-main-title"
            className="item-form-section"
          >
            <h3 id="item-main-title">Основные данные</h3>
            <div className="grid gap-x-5 gap-y-3 sm:grid-cols-2">
              <ReferenceSelect
                kind="categories"
                value={form.category_id}
                initialName={item?.category_name}
                disabled={locked}
                onChange={(category_id) => setForm({ ...form, category_id })}
              />
              <ReferenceSelect
                kind="manufacturers"
                value={form.manufacturer_id}
                initialName={item?.manufacturer_name}
                disabled={locked}
                onChange={(manufacturer_id) =>
                  setForm({ ...form, manufacturer_id })
                }
              />
              <Field label="Модель расходника">
                {(id) => (
                  <Input
                    id={id}
                    required
                    maxLength={200}
                    disabled={locked}
                    value={form.model}
                    onChange={(event) =>
                      setForm({ ...form, model: event.target.value })
                    }
                  />
                )}
              </Field>
              <Field label="Артикул">
                {(id) => (
                  <Input
                    id={id}
                    maxLength={100}
                    disabled={locked}
                    value={form.article}
                    onChange={(event) =>
                      setForm({ ...form, article: event.target.value })
                    }
                  />
                )}
              </Field>
              <Field label="Внутренний код">
                {(id) => (
                  <Input
                    id={id}
                    required
                    maxLength={50}
                    disabled={locked || !!item}
                    value={form.internal_code}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        internal_code: event.target.value.toUpperCase(),
                      })
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
                    disabled={locked}
                    value={form.min_stock}
                    onChange={(event) =>
                      setForm({
                        ...form,
                        min_stock: Number(event.target.value),
                      })
                    }
                  />
                )}
              </Field>
            </div>
          </section>
          <div className="grid gap-5 md:grid-cols-2">
            <section
              aria-labelledby="item-photos-title"
              className="item-form-section min-w-0"
            >
              <h3 id="item-photos-title">Фотографии</h3>
              {photos.error && (
                <ErrorState
                  error={photos.error}
                  onRetry={() => void photos.refetch()}
                />
              )}
              {!!photos.data?.items.length && (
                <div className="grid grid-cols-3 gap-2">
                  {photos.data.items
                    .filter((photo) => !removedPhotos.includes(photo.id))
                    .map((photo) => (
                      <figure
                        key={photo.id}
                        className="min-w-0 rounded-lg border border-border p-2"
                      >
                        <img
                          className="h-20 w-full object-contain"
                          src={sameOriginPhoto(photo.content_url)}
                          alt={`Сохранённая фотография${photo.is_primary ? ' · главная' : ''}`}
                        />
                        <div className="mt-1 flex flex-wrap gap-1">
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            disabled={pending}
                            aria-pressed={
                              primaryPhoto
                                ? primaryPhoto === photo.id
                                : photo.is_primary && !queue.primary
                            }
                            onClick={() => {
                              setPrimaryPhoto(photo.id);
                              queue.setPrimary(undefined);
                            }}
                          >
                            Главное
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            disabled={pending}
                            onClick={() => {
                              setRemovedPhotos([...removedPhotos, photo.id]);
                              if (primaryPhoto === photo.id)
                                setPrimaryPhoto(undefined);
                            }}
                          >
                            Убрать
                          </Button>
                        </div>
                      </figure>
                    ))}
                </div>
              )}
              <PhotoPicker
                queue={queue}
                existing={(photos.data?.total ?? 0) - removedPhotos.length}
                disabled={pending || (!!item && photos.isPending)}
                onPrimaryChange={() => setPrimaryPhoto(undefined)}
              />
            </section>
            <section
              aria-labelledby="item-compatibility-title"
              className="item-form-section min-w-0"
            >
              <h3 id="item-compatibility-title">Совместимость</h3>
              <Input
                aria-label="Поиск совместимых моделей"
                placeholder="Найти модель принтера"
                value={printerSearch}
                disabled={locked}
                onChange={(event) => setPrinterSearch(event.target.value)}
              />
              {printers.error ? (
                <ErrorState
                  error={printers.error}
                  onRetry={() => void printers.refetch()}
                />
              ) : compatibility.error ? (
                <ErrorState
                  error={compatibility.error}
                  onRetry={() => void compatibility.refetch()}
                />
              ) : (
                <div className="max-h-36 space-y-2 overflow-y-auto rounded-lg border border-border p-3">
                  {printers.isPending ? (
                    <p role="status" className="text-xs text-muted">
                      Загружаем модели…
                    </p>
                  ) : !availablePrinters.length ? (
                    <p className="text-xs text-muted">
                      Моделей пока нет. Их можно добавить в справочниках склада.
                    </p>
                  ) : !filteredPrinters.length ? (
                    <p className="text-xs text-muted">
                      Модели не найдены. Измените запрос.
                    </p>
                  ) : (
                    filteredPrinters.map((printer) => (
                      <label
                        key={printer.id}
                        className="flex items-start gap-2 text-sm"
                      >
                        <input
                          type="checkbox"
                          className="mt-1 accent-orange-600"
                          disabled={
                            locked ||
                            (!!item && compatibility.isPending) ||
                            (!!printer.archived_at &&
                              !selected.includes(printer.id))
                          }
                          checked={selected.includes(printer.id)}
                          onChange={(event) =>
                            setSelectedPrinters(
                              event.target.checked
                                ? [...selected, printer.id]
                                : selected.filter((id) => id !== printer.id),
                            )
                          }
                        />
                        <span className="break-words">
                          {printer.manufacturer_name} {printer.model}
                          {printer.archived_at
                            ? ' (архив — снимите выбор)'
                            : ''}
                        </span>
                      </label>
                    ))
                  )}
                </div>
              )}
              <p className="text-xs text-muted">
                Выбрано: {selected.length} из 100. Необязательно.
              </p>
            </section>
          </div>
          <section
            aria-labelledby="item-extra-title"
            className="item-form-section"
          >
            <h3 id="item-extra-title">Дополнительно</h3>
            <Field label="Описание">
              {(id) => (
                <textarea
                  id={id}
                  className="min-h-16 w-full resize-y rounded-lg border border-border px-3 py-2 text-sm"
                  rows={2}
                  maxLength={5000}
                  disabled={locked}
                  value={form.description}
                  onChange={(event) =>
                    setForm({ ...form, description: event.target.value })
                  }
                />
              )}
            </Field>
          </section>
        </div>
        <footer className="item-form-footer">
          <p className="hidden text-xs text-muted sm:block">
            Код товара нельзя изменить после создания.
          </p>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={pending}
              onClick={onClose}
            >
              Отмена
            </Button>
            <Button
              type="submit"
              disabled={
                pending ||
                !form.category_id ||
                !form.manufacturer_id ||
                selected.length > 100
              }
            >
              {pending
                ? 'Сохраняем…'
                : saved
                  ? 'Продолжить сохранение'
                  : 'Сохранить товар'}
            </Button>
          </div>
        </footer>
      </form>
    </ConfirmDialog>
  );
}
