import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
import { ItemForm } from '../features/inventory/ItemForm';
import { Photos } from '../features/inventory/Photos';

let calls: { path: string; options?: RequestInit }[];
let failUpload: boolean;
let failReference: boolean;
const saved = {
  id: 'item1',
  version: 1,
  internal_code: 'NEW',
  model: 'Модель',
};
beforeEach(() => {
  calls = [];
  failUpload = false;
  failReference = false;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (path: string, options?: RequestInit) => {
      calls.push({ path, options });
      if (path.endsWith('/auth/csrf'))
        return Response.json({ csrf_token: 'csrf' });
      if (
        path.endsWith('/manufacturers') &&
        options?.method === 'POST' &&
        failReference
      )
        return Response.json(
          {
            detail: {
              code: 'duplicate',
              message: 'Производитель уже существует.',
            },
          },
          { status: 409 },
        );
      if (path.endsWith('/manufacturers') && options?.method === 'POST')
        return Response.json({ id: 'new-maker', name: 'Новый производитель' });
      if (path.endsWith('/categories') && options?.method === 'POST')
        return Response.json({
          id: 'new-category',
          name: 'Кабели',
          code: 'cables',
        });
      if (path.includes('/photos') && options?.method === 'POST')
        return failUpload
          ? Response.json(
              {
                detail: { code: 'invalid_photo', message: 'Повреждённое фото' },
              },
              { status: 422 },
            )
          : Response.json({ id: 'photo' });
      if (path.endsWith('/items') && options?.method === 'POST')
        return Response.json(saved);
      if (path.endsWith('/compatibilities') && options?.method === 'PUT')
        return Response.json({ ...saved, version: 2 });
      if (path.includes('/printer-models?'))
        return Response.json({
          items: [
            {
              id: 'printer',
              model: 'Laser',
              manufacturer_name: 'Производитель',
            },
          ],
          total: 1,
        });
      if (path.includes('/manufacturers?'))
        return Response.json({
          items: [{ id: 'maker', name: 'Производитель' }],
          total: 1,
        });
      if (path.includes('/categories?'))
        return Response.json({
          items: [{ id: 'category', name: 'Картриджи' }],
          total: 1,
        });
      return Response.json({ items: [], total: 0 });
    }),
  );
  URL.createObjectURL = vi.fn(() => 'blob:preview');
  URL.revokeObjectURL = vi.fn();
});
function show(children: React.ReactNode) {
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      {children}
    </QueryClientProvider>,
  );
}
async function fill() {
  const events = userEvent.setup();
  await screen.findByRole('option', { name: 'Картриджи' });
  await screen.findByRole('option', { name: 'Производитель' });
  await events.selectOptions(screen.getByLabelText('Категория'), 'category');
  await events.selectOptions(screen.getByLabelText('Производитель'), 'maker');
  await events.type(screen.getByLabelText('Модель расходника'), 'Модель');
  return events;
}
it('создаёт справочники внутри карточки и сразу выбирает новые значения', async () => {
  show(<ItemForm onClose={() => {}} onSaved={() => {}} />);
  const events = userEvent.setup();
  await events.click(
    await screen.findByRole('button', { name: 'Новая категория' }),
  );
  await events.type(screen.getByLabelText('Код новой категории'), 'cables');
  await events.type(
    screen.getByLabelText('Название новой категории'),
    'Кабели',
  );
  await events.click(
    screen.getByRole('button', { name: 'Сохранить категорию' }),
  );
  await waitFor(() =>
    expect(screen.getByLabelText('Категория')).toHaveValue('new-category'),
  );
  await events.click(
    screen.getByRole('button', { name: 'Новый производитель' }),
  );
  await events.type(
    screen.getByLabelText('Название нового производителя'),
    'Новый производитель',
  );
  await events.click(
    screen.getByRole('button', { name: 'Сохранить производителя' }),
  );
  await waitFor(() =>
    expect(screen.getByLabelText('Производитель')).toHaveValue('new-maker'),
  );
  await events.click(
    screen.getByRole('button', { name: 'Открыть поиск производителя' }),
  );
  await events.type(screen.getByLabelText('Поиск производителя'), 'нов');
  await waitFor(() =>
    expect(
      calls.some((call) => call.path.includes('q=%D0%BD%D0%BE%D0%B2')),
    ).toBe(true),
  );
  expect(screen.getByLabelText('Производитель')).toHaveValue('new-maker');
  expect(
    calls.some(
      (call) => call.path.endsWith('/items') && call.options?.method === 'POST',
    ),
  ).toBe(false);
});
it('показывает два предварительных фото и сохраняет их после создания позиции', async () => {
  const onSaved = vi.fn();
  show(<ItemForm onClose={() => {}} onSaved={onSaved} />);
  const events = await fill();
  await events.upload(screen.getByLabelText('Загрузить фото'), [
    new File(['a'], 'a.png', { type: 'image/png' }),
    new File(['b'], 'b.png', { type: 'image/png' }),
  ]);
  expect(screen.getAllByRole('img', { name: /Предпросмотр/ })).toHaveLength(2);
  expect(calls.filter((call) => call.options?.method === 'POST')).toHaveLength(
    0,
  );
  await events.click(screen.getByRole('button', { name: 'Сохранить товар' }));
  await waitFor(() => expect(onSaved).toHaveBeenCalled());
  expect(
    calls.filter(
      (call) =>
        call.path.endsWith('/items/item1/photos') &&
        call.options?.method === 'POST',
    ),
  ).toHaveLength(2);
});
it('повтор после отказа фото не создаёт вторую позицию', async () => {
  const onSaved = vi.fn();
  show(<ItemForm onClose={() => {}} onSaved={onSaved} />);
  const events = await fill();
  await events.upload(
    screen.getByLabelText('Загрузить фото'),
    new File(['a'], 'a.png', { type: 'image/png' }),
  );
  failUpload = true;
  await events.click(screen.getByRole('button', { name: 'Сохранить товар' }));
  await screen.findByText(/Повреждённое фото/);
  expect(onSaved).not.toHaveBeenCalled();
  failUpload = false;
  await events.click(
    screen.getByRole('button', { name: 'Продолжить сохранение' }),
  );
  await waitFor(() => expect(onSaved).toHaveBeenCalled());
  expect(
    calls.filter(
      (call) => call.path.endsWith('/items') && call.options?.method === 'POST',
    ),
  ).toHaveLength(1);
});
it('ограничивает количество, тип и размер файлов до загрузки', async () => {
  show(<Photos itemId="item1" manage />);
  const events = userEvent.setup({ applyAccept: false });
  const input = await screen.findByLabelText('Загрузить фото');
  await waitFor(() => expect(input).toBeEnabled());
  await events.upload(
    input,
    new File(['x'], 'file.txt', { type: 'text/plain' }),
  );
  await screen.findByText(/Только JPEG, PNG или WebP/);
  await events.upload(
    input,
    new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'large.png', {
      type: 'image/png',
    }),
  );
  await screen.findByText(/превышает 5 МБ/);
  await events.upload(
    input,
    Array.from(
      { length: 6 },
      (_, i) => new File(['x'], `${i}.png`, { type: 'image/png' }),
    ),
  );
  await screen.findByText(/Не более 5 фотографий/);
  expect(calls.some((call) => call.options?.method === 'POST')).toBe(false);
});

it('открывает компактный вложенный справочник и возвращает фокус без потери карточки', async () => {
  show(<ItemForm onClose={() => {}} onSaved={() => {}} />);
  const events = userEvent.setup();
  await events.type(screen.getByLabelText('Внутренний код'), 'KEEP');
  const trigger = screen.getByRole('button', { name: 'Новая категория' });
  await events.click(trigger);
  const nested = screen.getByRole('dialog', { name: 'Новая категория' });
  await events.type(
    within(nested).getByLabelText('Код новой категории'),
    'кириллица',
  );
  await events.type(
    within(nested).getByLabelText('Название новой категории'),
    'Кабели',
  );
  await events.click(
    within(nested).getByRole('button', { name: 'Сохранить категорию' }),
  );
  expect(await within(nested).findByRole('alert')).toHaveTextContent(
    'корректный код категории либо оставьте код пустым для генерации',
  );
  expect(calls.some((call) => call.options?.method === 'POST')).toBe(false);
  await events.keyboard('{Escape}');
  await waitFor(() => expect(trigger).toHaveFocus());
  expect(screen.getByLabelText('Внутренний код')).toHaveValue('KEEP');
  expect(screen.getByRole('button', { name: 'Сохранить товар' })).toBeVisible();
  expect(screen.getByRole('button', { name: 'Отмена' })).toBeVisible();
});

it('сохраняет выбранную совместимость и главное фото вместе с товаром', async () => {
  const onSaved = vi.fn();
  show(<ItemForm onClose={() => {}} onSaved={onSaved} />);
  const events = await fill();
  await events.click(await screen.findByLabelText('Производитель Laser'));
  await events.upload(screen.getByLabelText('Загрузить фото'), [
    new File(['a'], 'first.png', { type: 'image/png' }),
    new File(['b'], 'second.png', { type: 'image/png' }),
  ]);
  await events.click(
    screen.getByRole('button', { name: 'Главное фото second.png' }),
  );
  expect(
    screen.getByRole('button', { name: 'Главное фото second.png' }),
  ).toHaveAttribute('aria-pressed', 'true');
  await events.click(screen.getByRole('button', { name: 'Сохранить товар' }));
  await waitFor(() => expect(onSaved).toHaveBeenCalled());
  const compatibility = calls.find((call) => call.options?.method === 'PUT');
  expect(JSON.parse(String(compatibility?.options?.body))).toEqual({
    version: 1,
    printer_model_ids: ['printer'],
  });
  expect(
    calls.some(
      (call) =>
        call.path.endsWith('/photos/photo') &&
        call.options?.method === 'PATCH' &&
        JSON.parse(String(call.options.body)).is_primary,
    ),
  ).toBe(true);
});

it('сохраняет ввод при дубликате справочника и сообщает о пустом поиске моделей', async () => {
  show(<ItemForm onClose={() => {}} onSaved={() => {}} />);
  const events = userEvent.setup();
  await events.type(
    screen.getByLabelText('Поиск совместимых моделей'),
    'absent',
  );
  expect(
    await screen.findByText('Модели не найдены. Измените запрос.'),
  ).toBeVisible();
  await events.click(
    screen.getByRole('button', { name: 'Новый производитель' }),
  );
  await events.type(
    screen.getByLabelText('Название нового производителя'),
    'Дубликат',
  );
  failReference = true;
  await events.click(
    screen.getByRole('button', { name: 'Сохранить производителя' }),
  );
  expect(await screen.findByRole('alert')).toHaveTextContent('уже существует');
  expect(screen.getByLabelText('Название нового производителя')).toHaveValue(
    'Дубликат',
  );
  expect(
    screen.getByRole('dialog', { name: 'Новый производитель' }),
  ).toBeVisible();
});
