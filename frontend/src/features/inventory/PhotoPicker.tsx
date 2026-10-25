import { useEffect, useRef, useState } from 'react';
import { Field, Notice } from '../../components/common';
import { Input } from '../../components/ui/input';
import { Button } from '../../components/ui/button';
import { request } from '../../lib/api';
import { Star, X } from 'lucide-react';
import type { Photo } from './types';

interface PendingPhoto {
  file: File;
  url: string;
  id: string;
}
export function usePhotoQueue() {
  const [photos, setPhotos] = useState<PendingPhoto[]>([]);
  const [primary, setPrimary] = useState<string>();
  const primaryUpload = useRef<string | undefined>(undefined);
  const current = useRef(photos);
  current.current = photos;
  useEffect(
    () => () =>
      current.current.forEach((photo) => URL.revokeObjectURL(photo.url)),
    [],
  );
  const remove = (id: string) => {
    setPrimary((previous) => (previous === id ? undefined : previous));
    setPhotos((previous) => {
      const removed = previous.find((photo) => photo.id === id);
      if (removed) URL.revokeObjectURL(removed.url);
      return previous.filter((photo) => photo.id !== id);
    });
  };
  function add(files: File[], existing: number) {
    if (existing + photos.length + files.length > 5)
      throw new Error(
        'Не более 5 фотографий на позицию. Уберите лишние снимки.',
      );
    for (const file of files) {
      if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type))
        throw new Error(
          'Только JPEG, PNG или WebP. Выберите фотографию поддерживаемого типа.',
        );
      if (file.size > 5 * 1024 * 1024)
        throw new Error('Размер фотографии превышает 5 МБ.');
    }
    setPhotos((previous) => [
      ...previous,
      ...files.map((file) => ({
        file,
        url: URL.createObjectURL(file),
        id: crypto.randomUUID(),
      })),
    ]);
  }
  async function upload(itemId: string) {
    for (const photo of photos) {
      const body = new FormData();
      body.append('file', photo.file);
      const uploaded = await request<Photo>(
        `/inventory/items/${itemId}/photos`,
        {
          method: 'POST',
          body,
        },
      );
      if (photo.id === primary) primaryUpload.current = uploaded.id;
      remove(photo.id);
    }
    if (primaryUpload.current) {
      await request(
        `/inventory/items/${itemId}/photos/${primaryUpload.current}`,
        { method: 'PATCH', body: { is_primary: true } },
      );
      primaryUpload.current = undefined;
    }
  }
  return { photos, add, remove, upload, primary, setPrimary };
}
export function PhotoPicker({
  queue,
  existing = 0,
  disabled = false,
  onPrimaryChange,
}: {
  queue: ReturnType<typeof usePhotoQueue>;
  existing?: number;
  disabled?: boolean;
  onPrimaryChange?: () => void;
}) {
  const [error, setError] = useState('');
  return (
    <div className="space-y-3">
      <Field
        label="Загрузить фото"
        hint="До 5 фото · JPEG, PNG, WebP · 5 МБ / 20 Мп. Загрузятся после сохранения."
      >
        {(id) => (
          <Input
            id={id}
            type="file"
            multiple
            accept="image/jpeg,image/png,image/webp"
            disabled={disabled || existing + queue.photos.length >= 5}
            onChange={(event) => {
              setError('');
              try {
                queue.add(Array.from(event.target.files ?? []), existing);
              } catch (error) {
                setError((error as Error).message);
              }
              event.target.value = '';
            }}
          />
        )}
      </Field>
      {error && <Notice>{error}</Notice>}
      <div className="grid grid-cols-3 gap-2">
        {queue.photos.map((photo) => (
          <figure
            key={photo.id}
            className="min-w-0 space-y-2 rounded-lg border border-border p-2"
          >
            <img
              className="h-20 w-full object-contain"
              src={photo.url}
              alt={`Предпросмотр ${photo.file.name}`}
            />
            <figcaption className="break-all text-xs text-muted">
              {photo.file.name}
            </figcaption>
            <div className="flex justify-between gap-1">
              <Button
                type="button"
                size="icon"
                variant="ghost"
                disabled={disabled}
                aria-label={`Главное фото ${photo.file.name}`}
                aria-pressed={queue.primary === photo.id}
                onClick={() => {
                  queue.setPrimary(photo.id);
                  onPrimaryChange?.();
                }}
              >
                <Star
                  aria-hidden="true"
                  className={
                    queue.primary === photo.id
                      ? 'fill-orange-500 text-orange-600'
                      : ''
                  }
                />
              </Button>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                disabled={disabled}
                aria-label={`Убрать выбранное фото ${photo.file.name}`}
                onClick={() => queue.remove(photo.id)}
              >
                <X aria-hidden="true" />
              </Button>
            </div>
          </figure>
        ))}
      </div>
    </div>
  );
}
