import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, expect, it, vi } from 'vitest';
import { AuthProvider } from '../auth';
import { AppRoutes } from '../App';

let permissions: string[];
let sent: RequestInit[];
let outcome: 'network' | 'stock' | 'success';
const item = {
  id: 'item1',
  internal_code: 'TEST-1',
  model: 'Тестовый картридж',
  manufacturer_name: 'Тест',
  category_name: 'Картриджи',
  balance: 10,
  min_stock: 2,
  version: 1,
  archived_at: null,
  primary_photo_url: null,
};
beforeEach(() => {
  permissions = ['inventory.read', 'inventory.issue'];
  sent = [];
  outcome = 'network';
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, options?: RequestInit) => {
      if (url.endsWith('/auth/csrf'))
        return Response.json({ csrf_token: 'test' });
      if (url.endsWith('/auth/me'))
        return Response.json({
          id: 'user1',
          display_name: 'Тест',
          permissions,
        });
      if (url.endsWith('/inventory/issues') && options?.method === 'POST') {
        sent.push(options);
        if (outcome === 'network') throw new TypeError('offline');
        if (outcome === 'stock')
          return Response.json(
            {
              detail: {
                code: 'insufficient_stock',
                message: 'Недостаточный остаток',
                items: [
                  { inventory_item_id: 'item1', available: 1, requested: 3 },
                ],
              },
            },
            { status: 409 },
          );
        return Response.json({
          id: 'doc1',
          number: 'INV-0001',
          document_type: 'issue',
          document_date: '2026-10-18',
          created_by_name: 'Тест',
          recipient_name: 'Получатель',
          items: [
            {
              inventory_item_id: 'item1',
              internal_code: 'TEST-1',
              model: item.model,
              quantity: 3,
              delta: -3,
            },
          ],
        });
      }
      if (url.includes('/inventory/items?'))
        return Response.json({ items: [item], total: 1 });
      if (url.includes('/directory/employees'))
        return Response.json({
          items: [
            {
              id: 'employee1',
              full_name: 'Получатель',
              personnel_number: '001',
              department_name: 'Отдел',
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
async function prepareIssue() {
  app('/issues');
  const events = userEvent.setup();
  await events.click(
    await screen.findByRole('button', { name: 'Добавить в корзину TEST-1' }),
  );
  const quantity = screen.getByLabelText('Количество TEST-1');
  await events.clear(quantity);
  await events.type(quantity, '3');
  await events.selectOptions(
    screen.getByLabelText('Сотрудник-получатель'),
    'employee1',
  );
  await events.click(screen.getByRole('button', { name: 'Проверить выдачу' }));
  await events.click(
    screen.getByRole('button', { name: 'Подтвердить выдачу' }),
  );
  return events;
}
it('после неизвестного результата блокирует изменения и повторяет тот же payload и ключ', async () => {
  const events = await prepareIssue();
  await screen.findByText(/Результат операции пока неизвестен/);
  expect(screen.getByLabelText('Количество TEST-1')).toHaveValue(3);
  expect(screen.getByLabelText('Количество TEST-1')).toBeDisabled();
  outcome = 'success';
  await events.click(
    screen.getByRole('button', { name: 'Повторить отправку' }),
  );
  await screen.findByText('INV-0001');
  expect(sent).toHaveLength(2);
  expect(sent[1].body).toBe(sent[0].body);
  expect(new Headers(sent[1].headers).get('Idempotency-Key')).toBe(
    new Headers(sent[0].headers).get('Idempotency-Key'),
  );
  expect(screen.queryByLabelText('Количество TEST-1')).not.toBeInTheDocument();
  expect(localStorage.length + sessionStorage.length).toBe(0);
});
it('конфликт остатка сохраняет корзину и показывает доступное количество', async () => {
  outcome = 'stock';
  await prepareIssue();
  expect(await screen.findByText(/Доступно: 1/)).toBeVisible();
  expect(screen.getByLabelText('Количество TEST-1')).toHaveValue(3);
  expect(screen.getByLabelText('Количество TEST-1')).toBeEnabled();
});
it('руководитель читает каталог без кнопок изменения', async () => {
  permissions = ['inventory.read'];
  app('/inventory');
  await screen.findByText('Тестовый картридж');
  expect(
    screen.queryByRole('button', { name: 'Создать позицию' }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole('link', { name: 'Поступление' }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole('button', { name: /Добавить в корзину/ }),
  ).not.toBeInTheDocument();
});
it('ИТ-специалист не может открыть поступление прямым маршрутом', async () => {
  app('/inventory/receipt');
  await waitFor(() =>
    expect(screen.getByText('Недостаточно прав')).toBeVisible(),
  );
});
