import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import { AuthProvider } from '../auth';
import { AppRoutes } from '../App';
import { sameOriginPhoto } from '../features/inventory/api';
const item = {
  id: 'item1',
  internal_code: 'CAT-1',
  model: 'Позиция для проверки',
  category_id: 'category1',
  category_name: 'Картриджи',
  manufacturer_id: 'maker1',
  manufacturer_name: 'Производитель',
  description: '',
  min_stock: 2,
  balance: 0,
  version: 4,
  archived_at: null,
};
let calls: { url: string; options?: RequestInit }[];
let failPatch: boolean;
beforeEach(() => {
  calls = [];
  failPatch = false;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, options?: RequestInit) => {
      calls.push({ url, options });
      const path = url.split('?')[0];
      if (path.endsWith('/auth/csrf'))
        return Response.json({ csrf_token: 'csrf' });
      if (path.endsWith('/auth/me'))
        return Response.json({
          id: 'admin',
          display_name: 'Тестовый оператор',
          permissions: [
            'inventory.read',
            'inventory.manage',
            'inventory.issue',
            'directory.manage',
          ],
        });
      if (options?.method === 'PATCH' && failPatch)
        return Response.json(
          {
            detail: {
              code: 'stale_version',
              message: 'Запись уже изменена. Обновите данные.',
            },
          },
          { status: 409 },
        );
      if (options?.method)
        return path.endsWith('/photos')
          ? Response.json({ id: 'photo1' })
          : Response.json({
              ...item,
              ...JSON.parse(String(options.body ?? '{}')),
            });
      if (path.endsWith('/inventory/items/item1')) return Response.json(item);
      if (path.endsWith('/inventory/items'))
        return Response.json({ items: [item], total: 1 });
      if (path.endsWith('/inventory/manufacturers'))
        return Response.json({
          items: [{ id: 'maker1', name: 'Производитель' }],
          total: 1,
        });
      if (path.endsWith('/inventory/categories'))
        return Response.json({
          items: [{ id: 'category1', name: 'Картриджи' }],
          total: 1,
        });
      if (path.endsWith('/inventory/printer-models'))
        return Response.json({
          items: [
            {
              id: 'printer1',
              model: 'Принтер 1',
              manufacturer_name: 'Другой производитель',
            },
            {
              id: 'printer2',
              model: 'Принтер 2',
              manufacturer_name: 'Другой производитель',
            },
          ],
          total: 2,
        });
      if (path.endsWith('/directory/departments'))
        return Response.json({
          items: [
            {
              id: 'department1',
              name: 'Тестовый отдел',
              code: 'DEP',
              version: 3,
              archived_at: null,
            },
          ],
          total: 1,
        });
      return Response.json({ items: [], total: 0 });
    }),
  );
});
function app(path: string) {
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}
it('создаёт позицию без редактируемого остатка', async () => {
  app('/inventory');
  const events = userEvent.setup();
  await events.click(
    await screen.findByRole('button', { name: 'Создать позицию' }),
  );
  const dialog = screen.getByRole('dialog');
  await events.type(within(dialog).getByLabelText('Внутренний код'), 'cat-new');
  await events.selectOptions(
    within(dialog).getByLabelText('Категория'),
    'category1',
  );
  await events.selectOptions(
    within(dialog).getByLabelText('Производитель'),
    'maker1',
  );
  await events.type(
    within(dialog).getByLabelText('Модель расходника'),
    'Новая модель',
  );
  await events.click(
    within(dialog).getByRole('button', { name: 'Сохранить товар' }),
  );
  await screen.findByRole('heading', { name: 'Позиция для проверки' });
  const sent = calls.find(
    (call) =>
      call.url.endsWith('/inventory/items') && call.options?.method === 'POST',
  )!;
  expect(JSON.parse(String(sent.options?.body))).toMatchObject({
    internal_code: 'CAT-NEW',
    model: 'Новая модель',
    min_stock: 0,
  });
  expect(JSON.parse(String(sent.options?.body))).not.toHaveProperty('balance');
});
it('stale version сохраняет редактируемую форму и отправляет версию', async () => {
  app('/inventory/items/item1');
  const events = userEvent.setup();
  await events.click(
    await screen.findByRole('button', { name: 'Редактировать' }),
  );
  const model = screen.getByLabelText('Модель расходника');
  await events.clear(model);
  await events.type(model, 'Исправленная модель');
  failPatch = true;
  await events.click(screen.getByRole('button', { name: 'Сохранить товар' }));
  await screen.findByText('Запись уже изменена. Обновите данные.');
  expect(model).toHaveValue('Исправленная модель');
  const sent = calls.find((call) => call.options?.method === 'PATCH')!;
  expect(JSON.parse(String(sent.options?.body))).toMatchObject({
    version: 4,
    model: 'Исправленная модель',
  });
  expect(JSON.parse(String(sent.options?.body))).not.toHaveProperty(
    'internal_code',
  );
});
it('сохраняет две совместимые модели другого производителя', async () => {
  app('/inventory/items/item1');
  const events = userEvent.setup();
  await events.click(
    await screen.findByRole('button', { name: 'Изменить совместимость' }),
  );
  await events.click(screen.getByLabelText('Другой производитель Принтер 1'));
  await events.click(screen.getByLabelText('Другой производитель Принтер 2'));
  await events.click(
    screen.getByRole('button', { name: 'Сохранить совместимость' }),
  );
  expect(
    JSON.parse(
      String(
        calls.find((call) => call.options?.method === 'PUT')?.options?.body,
      ),
    ),
  ).toEqual({ version: 4, printer_model_ids: ['printer1', 'printer2'] });
});
it('архив справочника требует подтверждения и версию', async () => {
  app('/directory');
  const events = userEvent.setup();
  await events.click(
    await screen.findByRole('button', { name: 'Архивировать' }),
  );
  expect(calls.some((call) => call.url.includes('/archive'))).toBe(false);
  await events.click(screen.getByRole('button', { name: 'Подтвердить' }));
  expect(
    JSON.parse(
      String(
        calls.find((call) => call.url.endsWith('/archive'))?.options?.body,
      ),
    ),
  ).toEqual({ version: 3 });
});
it('использует только same-origin защищённые URL фото', () => {
  expect(sameOriginPhoto('https://external.example/photo.png')).toBeUndefined();
  expect(sameOriginPhoto('/uploads/file.png')).toBeUndefined();
  expect(
    sameOriginPhoto('/api/v1/inventory/items/1/photos/2/content'),
  ).toContain('/api/v1/inventory/items/1/photos/2/content');
});
it('создаёт справочники в карточке и повторяет только незагруженные фото без второй позиции', async () => {
  vi.stubGlobal(
    'URL',
    Object.assign(URL, {
      createObjectURL: vi.fn(() => 'blob:preview'),
      revokeObjectURL: vi.fn(),
    }),
  );
  const previous = vi.mocked(fetch).getMockImplementation()!;
  let uploads = 0;
  let rejectPhoto = true;
  vi.mocked(fetch).mockImplementation(async (url, options) => {
    if (options?.method === 'POST' && String(url).endsWith('/photos')) {
      calls.push({ url: String(url), options });
      uploads++;
      if (uploads === 2 && rejectPhoto)
        return Response.json(
          { detail: { code: 'photo_error', message: 'Фото не загружено' } },
          { status: 503 },
        );
      return Response.json({ id: `photo${uploads}` });
    }
    if (
      options?.method === 'POST' &&
      /\/(categories|manufacturers)$/.test(String(url))
    ) {
      calls.push({ url: String(url), options });
      return Response.json({
        id: String(url).endsWith('/categories') ? 'new-category' : 'new-maker',
        ...JSON.parse(String(options.body)),
      });
    }
    return previous(url, options);
  });
  app('/inventory?create=1');
  const events = userEvent.setup();
  const dialog = await screen.findByRole('dialog');
  await events.click(
    within(dialog).getByRole('button', { name: 'Новая категория' }),
  );
  await events.type(screen.getByLabelText('Код новой категории'), 'cables');
  await events.type(
    screen.getByLabelText('Название новой категории'),
    'Кабели',
  );
  await events.click(
    screen.getByRole('button', { name: 'Сохранить категорию' }),
  );
  expect(within(dialog).getByLabelText('Категория')).toHaveValue(
    'new-category',
  );
  await events.click(
    within(dialog).getByRole('button', { name: 'Новый производитель' }),
  );
  await events.type(
    screen.getByLabelText('Название нового производителя'),
    'Новый производитель',
  );
  await events.click(
    screen.getByRole('button', { name: 'Сохранить производителя' }),
  );
  expect(within(dialog).getByLabelText('Производитель')).toHaveValue(
    'new-maker',
  );
  await events.type(
    within(dialog).getByLabelText('Внутренний код'),
    'new-photos',
  );
  await events.type(
    within(dialog).getByLabelText('Модель расходника'),
    'Кабель',
  );
  await events.upload(within(dialog).getByLabelText('Загрузить фото'), [
    new File(['a'], 'one.png', { type: 'image/png' }),
    new File(['b'], 'two.png', { type: 'image/png' }),
  ]);
  expect(within(dialog).getAllByRole('img')).toHaveLength(2);
  await events.click(
    within(dialog).getByRole('button', { name: 'Сохранить товар' }),
  );
  await screen.findByText(/Фото не загружено/);
  expect(within(dialog).getAllByRole('img')).toHaveLength(1);
  rejectPhoto = false;
  await events.click(
    within(dialog).getByRole('button', { name: 'Продолжить сохранение' }),
  );
  await screen.findByRole('heading', { name: 'Позиция для проверки' });
  expect(
    calls.filter(
      (call) =>
        call.url.endsWith('/inventory/items') &&
        call.options?.method === 'POST',
    ),
  ).toHaveLength(1);
  expect(uploads).toBe(3);
});
