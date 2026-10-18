import { useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import {
  EmptyState,
  ErrorState,
  LoadingState,
  Notice,
  Field,
  ConfirmDialog,
} from '../../components/common';
import { request } from '../../lib/api';
import { sameOriginPhoto, useList } from './api';
import type { Photo } from './types';
export function Photos({
  itemId,
  manage,
}: {
  itemId: string;
  manage: boolean;
}) {
  const client = useQueryClient();
  const query = useList<Photo>(`/inventory/items/${itemId}/photos`);
  const [error, setError] = useState('');
  const [pending, setPending] = useState(false);
  const [archive, setArchive] = useState<Photo>();
  const input = useRef<HTMLInputElement>(null);
  async function mutate(path: string, method: string, body?: unknown) {
    setPending(true);
    setError('');
    try {
      await request(`/inventory/items/${itemId}/photos${path}`, {
        method,
        body,
      });
      await client.invalidateQueries({ queryKey: ['warehouse'] });
      setArchive(undefined);
      if (input.current) input.current.value = '';
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setPending(false);
    }
  }
  return (
    <section className="space-y-4 rounded-xl border border-border bg-white p-5">
      <h2 className="text-lg font-semibold">Фотографии</h2>
      {error && <Notice>{error}</Notice>}
      {manage && (
        <Field
          label="Загрузить фото"
          hint="JPEG, PNG или WebP; до 5 МБ и 20 Мп, не более 5 фото."
        >
          {(id) => (
            <Input
              id={id}
              ref={input}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              disabled={pending || (query.data?.total ?? 0) >= 5}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (!file) return;
                if (file.size > 5 * 1024 * 1024) {
                  setError('Размер фотографии превышает 5 МБ.');
                  return;
                }
                const body = new FormData();
                body.append('file', file);
                void mutate('', 'POST', body);
              }}
            />
          )}
        </Field>
      )}
      {query.isPending ? (
        <LoadingState />
      ) : query.error ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : !query.data.items.length ? (
        <EmptyState
          title="Фотографий пока нет"
          description="Загрузите снимок, чтобы быстрее узнавать позицию."
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {query.data.items.map((photo) => (
            <figure
              key={photo.id}
              className="space-y-3 rounded-lg border border-border p-3"
            >
              <img
                className="h-48 w-full object-contain"
                src={sameOriginPhoto(photo.content_url)}
                alt={`Фотография позиции${photo.is_primary ? ' · главная' : ''}`}
              />
              <figcaption className="text-xs text-muted">
                {photo.is_primary ? 'Главное фото · ' : ''}
                {photo.width} × {photo.height}
              </figcaption>
              {manage && (
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    disabled={pending || photo.is_primary}
                    onClick={() =>
                      void mutate(`/${photo.id}`, 'PATCH', { is_primary: true })
                    }
                  >
                    Сделать главным
                  </Button>
                  <Button
                    variant="outline"
                    disabled={pending}
                    onClick={() => setArchive(photo)}
                  >
                    Убрать фото
                  </Button>
                  <Field label="Порядок фото">
                    {(id) => (
                      <Input
                        id={id}
                        key={photo.position}
                        type="number"
                        min={0}
                        max={1000}
                        step={1}
                        defaultValue={photo.position}
                        disabled={pending}
                        onBlur={(event) => {
                          const position = Number(event.target.value);
                          if (
                            Number.isInteger(position) &&
                            position >= 0 &&
                            position !== photo.position
                          )
                            void mutate(`/${photo.id}`, 'PATCH', { position });
                        }}
                      />
                    )}
                  </Field>
                </div>
              )}
            </figure>
          ))}
        </div>
      )}
      <ConfirmDialog
        open={!!archive}
        title="Убрать фотографию"
        description="Фотография будет архивирована. Файл и история сохранятся."
        onClose={() => setArchive(undefined)}
        pending={pending}
      >
        <div className="space-y-4">
          {error && <Notice>{error}</Notice>}
          <Button
            disabled={pending}
            onClick={() => void mutate(`/${archive?.id}/archive`, 'POST')}
          >
            Подтвердить
          </Button>
        </div>
      </ConfirmDialog>
    </section>
  );
}
