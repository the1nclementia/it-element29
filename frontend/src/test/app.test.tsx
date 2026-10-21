import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AppRoutes } from '../App';
import { AuthProvider } from '../auth';
import type {
  InventoryDocument,
  InventoryItem,
} from '../features/inventory/types';

const user = {
  id: '1',
  username: 'manager',
  display_name: 'Тестовый руководитель',
  role: 'manager',
  role_name: 'Руководитель',
  permissions: ['dashboard.read', 'settings.read', 'inventory.read'],
  is_active: true,
  must_change_password: false,
  created_at: '2026-01-01T00:00:00Z',
};
let currentUser: typeof user | null;
let requests: { path: string; options?: RequestInit }[];
let dashboardDocuments: InventoryDocument[];
let dashboardItems: InventoryItem[];
let documentFailure: boolean;
beforeEach(() => {
  currentUser = { ...user };
  requests = [];
  dashboardDocuments = [];
  dashboardItems = [];
  documentFailure = false;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (input: string, options?: RequestInit) => {
      const path = String(input);
      requests.push({ path, options });
      if (path.endsWith('/auth/csrf'))
        return Response.json({ csrf_token: 'test-csrf' });
      if (path.endsWith('/auth/me'))
        return currentUser
          ? Response.json(currentUser)
          : Response.json(
              {
                detail: { code: 'unauthorized', message: 'Войдите в систему' },
              },
              { status: 401 },
            );
      if (path.endsWith('/auth/login'))
        return Response.json(
          {
            detail: {
              code: 'invalid_credentials',
              message: 'Неверный логин или пароль',
            },
          },
          { status: 401 },
        );
      if (path.endsWith('/auth/logout')) {
        currentUser = null;
        return new Response(null, { status: 204 });
      }
      if (path.endsWith('/auth/password')) {
        currentUser = { ...currentUser!, must_change_password: false };
        return Response.json({ user: currentUser, csrf_token: 'rotated' });
      }
      if (path.endsWith('/dashboard'))
        return Response.json({
          metrics: [
            {
              key: 'cartridge_balance',
              label: 'Картриджей на складе',
              value: null,
              available: true,
            },
            {
              key: 'issues_today',
              label: 'Выдач сегодня',
              value: 2,
              available: true,
            },
            {
              key: 'low_stock',
              label: 'Низкий остаток',
              value: 1,
              available: true,
            },
            {
              key: 'equipment_total',
              label: 'Всего оборудования',
              value: null,
              available: false,
            },
          ],
          recent_events: [],
        });
      if (path.includes('/inventory/documents'))
        return documentFailure
          ? Response.json(
              {
                detail: {
                  code: 'unavailable',
                  message: 'Документы временно недоступны',
                },
              },
              { status: 503 },
            )
          : Response.json({
              items: dashboardDocuments,
              total: dashboardDocuments.length,
            });
      if (path.includes('/inventory/items?'))
        return Response.json({
          items: dashboardItems,
          total: dashboardItems.length,
        });
      if (path.includes('/users') && options?.method)
        return options.method === 'POST' && path.endsWith('reset-password')
          ? new Response(null, { status: 204 })
          : Response.json({ ...user, id: '2' });
      if (path.includes('/users'))
        return Response.json({
          items: [
            currentUser,
            {
              ...user,
              id: '2',
              username: 'other',
              display_name: 'Другой сотрудник',
            },
          ],
          total: 2,
        });
      if (path.endsWith('/roles'))
        return Response.json({
          items: [
            { code: 'manager', name: 'Руководитель', permissions: [] },
            { code: 'administrator', name: 'Администратор', permissions: [] },
          ],
        });
      return Response.json(
        { detail: { code: 'not_found', message: 'Не найдено' } },
        { status: 404 },
      );
    }),
  );
});
function app(path = '/') {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <AuthProvider>
          <AppRoutes />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
}
describe('Авторизация и интерфейс', () => {
  it('показывает и скрывает введённый пароль без отправки формы', async () => {
    currentUser = null;
    app('/login');
    const events = userEvent.setup();
    const password = await screen.findByLabelText('Пароль');
    await events.type(password, 'example-password');
    expect(password).toHaveAttribute('type', 'password');
    await events.click(screen.getByRole('button', { name: 'Показать пароль' }));
    expect(password).toHaveAttribute('type', 'text');
    expect(password).toHaveValue('example-password');
    await events.click(screen.getByRole('button', { name: 'Скрыть пароль' }));
    expect(password).toHaveAttribute('type', 'password');
    expect(
      requests.some((request) => request.path.endsWith('/auth/login')),
    ).toBe(false);
  });
  it('восстанавливает сессию и показывает null как отсутствие данных, не ноль', async () => {
    app();
    expect(
      await screen.findByRole('heading', { name: 'Добро пожаловать!' }),
    ).toBeVisible();
    expect(await screen.findByText('Картриджей на складе')).toBeVisible();
    expect(screen.queryByText('Всего оборудования')).not.toBeInTheDocument();
    expect(screen.getByLabelText('Значение недоступно')).toHaveTextContent('—');
    expect(
      screen.queryByRole('link', { name: 'Пользователи' }),
    ).not.toBeInTheDocument();
    expect(requests.some((r) => r.path.endsWith('/auth/csrf'))).toBe(true);
  });
  it('показывает только доступные складские действия и реальные пустые состояния', async () => {
    app();
    expect(
      await screen.findByRole('link', { name: /Открыть склад/ }),
    ).toHaveAttribute('href', '/inventory');
    expect(
      screen.queryByRole('link', { name: /Добавить номенклатуру/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: /Новое поступление/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: /Оформить выдачу/ }),
    ).not.toBeInTheDocument();
    expect(await screen.findByText('Документов пока нет')).toBeVisible();
    expect(await screen.findByText('Все остатки в норме')).toBeVisible();
  });
  it('даёт разрешённые быстрые действия по рабочим адресам', async () => {
    currentUser = {
      ...user,
      permissions: [...user.permissions, 'inventory.manage', 'inventory.issue'],
    };
    app();
    expect(
      await screen.findByRole('link', { name: /Добавить номенклатуру/ }),
    ).toHaveAttribute('href', '/inventory?create=1');
    expect(
      screen.getByRole('link', { name: /Новое поступление/ }),
    ).toHaveAttribute('href', '/inventory/receipt');
    expect(
      screen.getByRole('link', { name: /Оформить выдачу/ }),
    ).toHaveAttribute('href', '/issues');
  });
  it('показывает полученные документы и остатки со ссылками на карточки', async () => {
    dashboardDocuments = [
      {
        id: 'doc-1',
        number: 'INV-00042',
        document_type: 'receipt',
        document_date: '2026-10-20',
        created_at: '2026-10-20T09:00:00Z',
        created_by_id: '1',
        created_by_name: user.display_name,
        recipient_employee_id: null,
        recipient_name: null,
        recipient_personnel_number: null,
        recipient_department: null,
        recipient_room: null,
        supplier_name: null,
        comment: null,
        receipt_purpose: 'purchase',
        external_number: null,
        reversal_of_id: null,
        reason: null,
        is_cancelled: true,
        reversal_id: 'reversal-1',
        reversal_number: 'INV-00043',
        items: [],
      },
    ];
    dashboardItems = [
      {
        id: 'item-1',
        version: 1,
        archived_at: null,
        created_at: '2026-10-20T09:00:00Z',
        updated_at: '2026-10-20T09:00:00Z',
        internal_code: 'TEST-042',
        category_id: 'cat-1',
        category_name: 'Картриджи',
        manufacturer_id: 'maker-1',
        manufacturer_name: 'Тест',
        model: 'Картридж 42',
        article: null,
        description: '',
        min_stock: 3,
        balance: 1,
        unit: 'pcs',
        is_low_stock: true,
        primary_photo_url: null,
      },
    ];
    app();
    const document = await screen.findByRole('link', { name: /INV-00042/ });
    expect(document).toHaveAttribute('href', '/inventory/documents/doc-1');
    expect(document).toHaveTextContent('Отменён');
    const item = await screen.findByRole('link', { name: /Тест Картридж 42/ });
    expect(item).toHaveAttribute('href', '/inventory/items/item-1');
    expect(item).toHaveTextContent('Минимум 3 шт.');
    expect(item).toHaveTextContent('1 шт.');
    expect(screen.getByRole('link', { name: /Показать все/ })).toHaveAttribute(
      'href',
      '/inventory?low_stock=true',
    );
  });
  it('изолирует ошибку документов и повторяет загрузку по кнопке', async () => {
    documentFailure = true;
    app();
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Документы временно недоступны',
    );
    expect(screen.getByText('Все остатки в норме')).toBeVisible();
    expect(screen.queryByText('Документов пока нет')).not.toBeInTheDocument();
    documentFailure = false;
    await userEvent.click(screen.getByRole('button', { name: 'Повторить' }));
    expect(await screen.findByText('Документов пока нет')).toBeVisible();
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });
  it('не запрашивает и не показывает складские списки без inventory.read', async () => {
    currentUser = { ...user, permissions: ['dashboard.read', 'settings.read'] };
    app();
    await screen.findByRole('heading', { name: 'Добро пожаловать!' });
    expect(
      screen.queryByRole('heading', { name: 'Последние документы' }),
    ).not.toBeInTheDocument();
    expect(requests.some(({ path }) => path.includes('/inventory/'))).toBe(
      false,
    );
  });
  it('открывает историю и отчёты для чтения склада, черновики — для управления', async () => {
    currentUser = {
      ...user,
      permissions: [...user.permissions, 'inventory.manage'],
    };
    app();
    const navigation = within(await screen.findByRole('navigation'));
    expect(navigation.getByRole('link', { name: 'История' })).toHaveAttribute(
      'href',
      '/history',
    );
    expect(navigation.getByRole('link', { name: 'Отчёты' })).toHaveAttribute(
      'href',
      '/reports',
    );
    expect(
      navigation.getByRole('link', { name: 'Мои черновики' }),
    ).toHaveAttribute('href', '/inventory/drafts');
    expect(
      navigation.getByRole('link', { name: 'Поступления' }),
    ).toHaveAttribute('href', '/inventory/receipt');
  });
  it('закрывает прямой маршрут пользователей для роли без users.manage', async () => {
    app('/users');
    expect(
      await screen.findByRole('heading', { name: 'Недостаточно прав' }),
    ).toBeVisible();
    expect(requests.some((r) => r.path.includes('/users'))).toBe(false);
  });
  it('помечает будущий модуль как находящийся в разработке', async () => {
    currentUser = {
      ...user,
      permissions: [...user.permissions, 'equipment.read'],
    };
    app('/equipment');
    expect(
      await screen.findByRole('heading', { name: 'Оборудование' }),
    ).toBeVisible();
    expect(screen.getByText('В разработке')).toBeVisible();
    expect(
      screen.queryByRole('button', { name: /добавить|выдать|создать/i }),
    ).not.toBeInTheDocument();
  });
  it('истечение сессии на API очищает загруженные данные и открывает вход', async () => {
    const client = app();
    await screen.findByRole('heading', { name: 'Добро пожаловать!' });
    vi.mocked(fetch).mockResolvedValueOnce(
      Response.json(
        { detail: { code: 'unauthorized', message: 'Войдите в систему' } },
        { status: 401 },
      ),
    );
    await client.refetchQueries({ queryKey: ['dashboard'] });
    expect(
      await screen.findByRole('button', { name: 'Войти в систему' }),
    ).toBeVisible();
    expect(client.getQueryData(['dashboard'])).toBeUndefined();
    expect(screen.queryByText('Всего оборудования')).not.toBeInTheDocument();
  });
  it('обязательная смена пароля ведёт в настройки и позволяет сменить пароль', async () => {
    currentUser = { ...user, must_change_password: true };
    app('/users');
    expect(
      await screen.findByRole('heading', { name: 'Настройки' }),
    ).toBeVisible();
    const events = userEvent.setup();
    await events.type(
      screen.getByLabelText('Текущий пароль'),
      'old-password-test',
    );
    await events.type(
      screen.getByLabelText('Новый пароль'),
      'new-password-test',
    );
    await events.type(
      screen.getByLabelText('Повторите новый пароль'),
      'new-password-test',
    );
    await events.click(screen.getByRole('button', { name: 'Изменить пароль' }));
    expect(await screen.findByText('Пароль успешно изменён')).toBeVisible();
    const request = requests.find((r) => r.path.endsWith('/auth/password'))!;
    expect(new Headers(request.options?.headers).get('X-CSRF-Token')).toBe(
      'test-csrf',
    );
    expect(request.options?.credentials).toBe('same-origin');
  });
  it('не сбрасывает форму при неверном пароле входа', async () => {
    currentUser = null;
    app('/');
    const events = userEvent.setup();
    await events.type(await screen.findByLabelText('Логин'), 'person');
    await events.type(screen.getByLabelText('Пароль'), 'incorrect-password');
    await events.click(screen.getByRole('button', { name: 'Войти в систему' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Неверный логин или пароль',
    );
    expect(screen.getByLabelText('Логин')).toHaveValue('person');
  });
  it('выход очищает данные и возвращает форму входа', async () => {
    const client = app();
    await screen.findByRole('heading', { name: 'Добро пожаловать!' });
    await userEvent.click(screen.getByRole('button', { name: 'Выйти' }));
    await screen.findByRole('button', { name: 'Войти в систему' });
    expect(client.getQueryData(['dashboard'])).toBeUndefined();
  });
  it('администратору доступны создание, роль, блокировка и сброс; свои роль и блокировка закрыты', async () => {
    currentUser = {
      ...user,
      role: 'administrator',
      role_name: 'Администратор',
      permissions: [...user.permissions, 'users.manage'],
    };
    app('/users');
    expect(
      await screen.findByRole('button', { name: 'Добавить пользователя' }),
    ).toBeVisible();
    const self = await screen.findByRole('row', {
      name: /Тестовый руководитель/,
    });
    expect(
      within(self).getByRole('button', { name: 'Изменить роль' }),
    ).toBeDisabled();
    expect(
      within(self).getByRole('button', { name: 'Заблокировать' }),
    ).toBeDisabled();
    const other = screen.getByRole('row', { name: /Другой сотрудник/ });
    await userEvent.click(
      within(other).getByRole('button', { name: 'Заблокировать' }),
    );
    expect(await screen.findByRole('dialog')).toHaveTextContent(
      'Другой сотрудник',
    );
    expect(
      screen.getByRole('button', { name: 'Подтвердить блокировку' }),
    ).toBeVisible();
    await userEvent.click(screen.getByRole('button', { name: 'Отмена' }));
    await userEvent.click(
      screen.getByRole('button', { name: 'Добавить пользователя' }),
    );
    expect(await screen.findByRole('dialog')).toHaveTextContent(
      'Временный пароль',
    );
    await waitFor(() =>
      expect(screen.getByLabelText('Временный пароль')).toHaveAttribute(
        'type',
        'password',
      ),
    );
  });
  it('создаёт пользователя с временным паролем через CSRF API и закрывает диалог после ответа', async () => {
    currentUser = {
      ...user,
      role: 'administrator',
      permissions: [...user.permissions, 'users.manage'],
    };
    app('/users');
    const events = userEvent.setup();
    await events.click(
      await screen.findByRole('button', { name: 'Добавить пользователя' }),
    );
    await events.type(
      screen.getByLabelText('Имя сотрудника'),
      'Новый сотрудник',
    );
    await events.type(screen.getByLabelText('Логин'), 'new.person');
    await events.selectOptions(screen.getByLabelText('Роль'), 'manager');
    await events.type(
      screen.getByLabelText('Временный пароль'),
      'temporary-password',
    );
    await events.click(
      screen.getByRole('button', { name: 'Создать пользователя' }),
    );
    expect(
      await screen.findByText(
        'Пользователь создан. При входе потребуется сменить пароль.',
      ),
    ).toBeVisible();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    const sent = requests.find(
      (r) => r.path.endsWith('/users') && r.options?.method === 'POST',
    )!;
    expect(JSON.parse(sent.options!.body as string)).toEqual({
      username: 'new.person',
      display_name: 'Новый сотрудник',
      role: 'manager',
      password: 'temporary-password',
    });
    expect(new Headers(sent.options?.headers).get('X-CSRF-Token')).toBe(
      'test-csrf',
    );
  });
  it('блокировка требует подтверждения и отправляет is_active=false', async () => {
    currentUser = {
      ...user,
      role: 'administrator',
      permissions: [...user.permissions, 'users.manage'],
    };
    app('/users');
    const other = await screen.findByRole('row', { name: /Другой сотрудник/ });
    await userEvent.click(
      within(other).getByRole('button', { name: 'Заблокировать' }),
    );
    expect(requests.some((r) => r.options?.method === 'PATCH')).toBe(false);
    await userEvent.click(
      screen.getByRole('button', { name: 'Подтвердить блокировку' }),
    );
    expect(
      await screen.findByText(
        'Пользователь заблокирован. Активные сессии отозваны.',
      ),
    ).toBeVisible();
    expect(
      JSON.parse(
        requests.find(
          (r) => r.path.endsWith('/users/2') && r.options?.method === 'PATCH',
        )!.options!.body as string,
      ),
    ).toEqual({ is_active: false });
  });
});
