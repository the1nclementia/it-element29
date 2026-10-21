import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { expect, it, vi } from 'vitest';
import { Reports } from '../pages/Reports';

it('выгружает движения с выбранным типом и получателем', async () => {
  const urls: string[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string) => {
      urls.push(input);
      if (input.includes('/directory/employees'))
        return Response.json({
          items: [
            {
              id: 'employee1',
              full_name: 'Получатель',
              personnel_number: '001',
            },
          ],
          total: 1,
        });
      if (input.includes('/exports/')) return new Response(new Blob(['xlsx']));
      return Response.json({ items: [], total: 0 });
    }),
  );
  URL.createObjectURL = vi.fn(() => 'blob:export');
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <Reports />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  const events = userEvent.setup();
  await events.selectOptions(
    await screen.findByLabelText('Тип движения'),
    'issue',
  );
  await screen.findByRole('option', { name: 'Получатель · 001' });
  await events.selectOptions(
    screen.getByLabelText('Получатель отчёта'),
    'employee1',
  );
  await events.click(
    screen.getByRole('button', { name: 'Скачать движения в Excel' }),
  );
  await waitFor(() =>
    expect(
      urls.some((url) =>
        url.includes(
          '/exports/movements.xlsx?document_type=issue&recipient_employee_id=employee1',
        ),
      ),
    ).toBe(true),
  );
});
