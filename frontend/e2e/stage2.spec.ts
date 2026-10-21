import { randomBytes } from 'node:crypto';
import { test, expect, type Page, type BrowserContext } from '@playwright/test';

const admin = process.env.E2E_ADMIN_USERNAME ?? 'acceptance_admin';
const adminPassword = process.env.E2E_ADMIN_PASSWORD!;
const origin = new URL(process.env.E2E_BASE_URL!).origin;
const temporary = () => `Test-only-${randomBytes(12).toString('hex')}`;

async function login(page: Page, username = admin, password = adminPassword) {
  await page.goto('/login');
  await page.getByLabel('Логин', { exact: true }).fill(username);
  await page.getByLabel('Пароль', { exact: true }).fill(password);
  await page
    .getByRole('button', { name: 'Войти в систему', exact: true })
    .click();
}

async function mutate(context: BrowserContext, path: string, data: object) {
  const csrf = await context.request.get('/api/v1/auth/csrf');
  const token = (await csrf.json()).csrf_token;
  return context.request.post(`/api/v1${path}`, {
    headers: { Origin: origin, 'X-CSRF-Token': token },
    data,
  });
}

test('вход, неверный пароль, refresh, cookie, пустой обзор и выход', async ({
  page,
  context,
}) => {
  await page.goto('/users');
  await expect(page).toHaveURL(/\/login$/);
  await login(page, admin, 'Incorrect-test-password');
  await expect(
    page.getByText('Неверный логин или пароль.', { exact: true }),
  ).toBeVisible();
  await login(page);
  await expect(
    page.getByRole('heading', { name: 'Добро пожаловать!', exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText('Данные появятся после запуска модуля', { exact: true }),
  ).toHaveCount(0);
  for (const label of [
    'Остаток картриджей',
    'Выдачи за сегодня',
    'Низкие остатки',
  ]) {
    await expect(page.getByText(label, { exact: true })).toBeVisible();
  }
  const cookie = (await context.cookies()).find(
    (item) => item.name === 'element29_session',
  );
  expect(cookie?.httpOnly).toBe(true);
  expect(cookie?.sameSite).toBe('Lax');
  expect(await page.evaluate(() => document.cookie)).not.toContain(
    'element29_session',
  );
  expect(
    await page.evaluate(() => [localStorage.length, sessionStorage.length]),
  ).toEqual([0, 0]);
  await page.reload();
  await expect(
    page.getByRole('heading', { name: 'Добро пожаловать!', exact: true }),
  ).toBeVisible();
  await page.goto('/equipment');
  await expect(page.getByText('Раздел готовится к запуску')).toBeVisible();
  await page.reload();
  await expect(page.getByText('Раздел готовится к запуску')).toBeVisible();
  await page.getByRole('button', { name: 'Выйти', exact: true }).click();
  await expect(page).toHaveURL(/\/login$/);
  expect((await context.request.get('/api/v1/auth/me')).status()).toBe(401);
});

test('управление пользователем, обязательная смена, роль, сброс и блокировка', async ({
  page,
  browser,
}) => {
  await login(page);
  await page.getByRole('link', { name: 'Пользователи', exact: true }).click();
  await page
    .getByRole('button', { name: 'Добавить пользователя', exact: true })
    .click();
  const username = `e2e_${randomBytes(5).toString('hex')}`;
  const password = temporary();
  const changed = temporary();
  const reset = temporary();
  const dialog = page.getByRole('dialog');
  await dialog
    .getByLabel('Имя сотрудника', { exact: true })
    .fill('Тестовый сотрудник E2E');
  await dialog.getByLabel('Логин', { exact: true }).fill(username);
  await dialog.getByLabel('Роль', { exact: true }).selectOption('manager');
  await dialog.getByLabel('Временный пароль', { exact: true }).fill(password);
  await dialog.getByRole('button', { name: 'Создать пользователя' }).click();
  await expect(dialog).not.toBeVisible();
  const row = page.getByRole('row').filter({ hasText: username });
  await expect(row).toBeVisible();

  const member = await browser.newContext({ baseURL: origin });
  try {
    const memberPage = await member.newPage();
    await login(memberPage, username, password);
    await expect(memberPage).toHaveURL(/\/settings$/);
    expect((await member.request.get('/api/v1/dashboard')).status()).toBe(403);
    await memberPage
      .getByLabel('Текущий пароль', { exact: true })
      .fill(password);
    await memberPage.getByLabel('Новый пароль', { exact: true }).fill(changed);
    await memberPage
      .getByLabel('Повторите новый пароль', { exact: true })
      .fill(changed);
    await memberPage
      .getByRole('button', { name: 'Изменить пароль', exact: true })
      .click();
    await expect(
      memberPage.getByText('Пароль успешно изменён', { exact: true }),
    ).toBeVisible();
    await memberPage.goto('/users');
    await expect(
      memberPage.getByText('Этот раздел недоступен вашей роли.', {
        exact: false,
      }),
    ).toBeVisible();
    expect((await member.request.get('/api/v1/users')).status()).toBe(403);

    await row
      .getByRole('button', { name: 'Изменить роль', exact: true })
      .click();
    await dialog
      .getByLabel('Роль', { exact: true })
      .selectOption('storekeeper');
    await dialog.getByRole('button', { name: 'Сохранить роль' }).click();
    await expect(dialog).not.toBeVisible();
    expect((await member.request.get('/api/v1/auth/me')).status()).toBe(401);
    await login(memberPage, username, changed);
    await expect(
      memberPage.getByRole('heading', {
        name: 'Добро пожаловать!',
        exact: true,
      }),
    ).toBeVisible();
    await expect(
      memberPage.getByRole('link', { name: 'Выдача', exact: true }),
    ).toBeVisible();

    await row
      .getByRole('button', { name: 'Сбросить пароль', exact: true })
      .click();
    await dialog.getByLabel('Временный пароль', { exact: true }).fill(reset);
    await dialog.getByRole('button', { name: 'Подтвердить сброс' }).click();
    await expect(dialog).not.toBeVisible();
    expect((await member.request.get('/api/v1/auth/me')).status()).toBe(401);
    await login(memberPage, username, reset);
    await expect(memberPage).toHaveURL(/\/settings$/);
    await row
      .getByRole('button', { name: 'Заблокировать', exact: true })
      .click();
    await dialog
      .getByRole('button', { name: 'Подтвердить блокировку' })
      .click();
    await expect(dialog).not.toBeVisible();
    expect((await member.request.get('/api/v1/auth/me')).status()).toBe(401);
    await login(memberPage, username, reset);
    await expect(
      memberPage.getByText('Неверный логин или пароль.', { exact: true }),
    ).toBeVisible();
    await row
      .getByRole('button', { name: 'Разблокировать', exact: true })
      .click();
    await dialog
      .getByRole('button', { name: 'Подтвердить разблокировку' })
      .click();
    await expect(dialog).not.toBeVisible();
    await login(memberPage, username, reset);
    await expect(memberPage).toHaveURL(/\/settings$/);
  } finally {
    await member.close();
  }
});

for (const role of [
  'administrator',
  'it_specialist',
  'storekeeper',
  'manager',
]) {
  test(`меню и серверные права: ${role}`, async ({
    page,
    context,
    browser,
  }) => {
    await login(page);
    await expect(
      page.getByRole('heading', { name: 'Добро пожаловать!', exact: true }),
    ).toBeVisible();
    const username = `role_${randomBytes(5).toString('hex')}`;
    const password = temporary();
    expect(
      (
        await mutate(context, '/users', {
          username,
          display_name: 'Проверка роли E2E',
          role,
          password,
        })
      ).status(),
    ).toBe(201);
    const member = await browser.newContext({ baseURL: origin });
    try {
      const memberPage = await member.newPage();
      await login(memberPage, username, password);
      await expect(memberPage).toHaveURL(/\/settings$/);
      expect(
        (
          await mutate(member, '/auth/password', {
            current_password: password,
            new_password: temporary(),
          })
        ).status(),
      ).toBe(200);
      await memberPage.goto('/');
      await expect(
        memberPage.getByRole('heading', {
          name: 'Добро пожаловать!',
          exact: true,
        }),
      ).toBeVisible();
      await expect(
        memberPage.getByRole('link', { name: 'Пользователи', exact: true }),
      ).toHaveCount(role === 'administrator' ? 1 : 0);
      await expect(
        memberPage.getByRole('link', { name: 'Выдача', exact: true }),
      ).toHaveCount(role === 'manager' ? 0 : 1);
      expect((await member.request.get('/api/v1/users')).status()).toBe(
        role === 'administrator' ? 200 : 403,
      );
    } finally {
      await member.close();
    }
  });
}

test('мобильная навигация и отсутствие горизонтального переполнения', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page);
  await expect(
    page.getByRole('heading', { name: 'Добро пожаловать!', exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.getByRole('button', { name: 'Открыть меню' }).click();
  await page
    .getByRole('dialog')
    .getByRole('link', { name: 'Склад', exact: true })
    .click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await expect(
    page.getByRole('heading', { name: 'Склад', exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: '../.scratch/stage2-mobile.png',
    fullPage: true,
  });
});

test('визуальный контроль desktop', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await login(page);
  await expect(
    page.getByRole('heading', { name: 'Добро пожаловать!', exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: '../.scratch/stage2-desktop.png',
    fullPage: true,
  });
});
