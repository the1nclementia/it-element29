import { beforeEach, expect, it, vi } from 'vitest';
import { request, setCsrf } from '../lib/api';

beforeEach(() => setCsrf('csrf-test'));
it('передаёт multipart без JSON Content-Type и сохраняет CSRF/cookie', async () => {
  const fetcher = vi.fn().mockResolvedValue(Response.json({ id: 'photo' }));
  vi.stubGlobal('fetch', fetcher);
  const body = new FormData();
  body.append('file', new File(['test'], 'test.png', { type: 'image/png' }));
  await request('/inventory/items/item/photos', { method: 'POST', body });
  const options = fetcher.mock.calls[0][1];
  expect(options.body).toBe(body);
  expect(options.headers.has('Content-Type')).toBe(false);
  expect(options.headers.get('X-CSRF-Token')).toBe('csrf-test');
  expect(options.credentials).toBe('same-origin');
});
it('сохраняет структурированные строки ошибки остатка', async () => {
  const detail = {
    code: 'insufficient_stock',
    message: 'Недостаточно остатка',
    items: [{ inventory_item_id: 'item', available: 2, requested: 3 }],
  };
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(Response.json({ detail }, { status: 409 })),
  );
  await expect(
    request('/inventory/issues', { method: 'POST', body: {} }),
  ).rejects.toMatchObject({ status: 409, detail });
});
it('повреждённый успешный ответ считается неизвестным сетевым результатом', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(new Response('incomplete', { status: 201 })),
  );
  await expect(
    request('/inventory/issues', { method: 'POST', body: {} }),
  ).rejects.toMatchObject({ status: 0, code: 'network' });
});
