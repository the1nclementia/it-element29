import { randomBytes, randomUUID } from 'node:crypto';
import {
  test,
  expect,
  type Page,
  type BrowserContext,
  type Browser,
} from '@playwright/test';

const origin = new URL(process.env.E2E_BASE_URL!).origin;
const admin = process.env.E2E_ADMIN_USERNAME ?? 'acceptance_admin';
const password = process.env.E2E_ADMIN_PASSWORD!;
const unique = () => randomBytes(5).toString('hex');
const secret = () => `Synthetic-${randomBytes(15).toString('hex')}`;
const visualPath = (name: string) =>
  `../.scratch/stage3-acceptance/visual/${name}.png`;
async function login(page: Page, username = admin, value = password) {
  await page.goto('/login');
  await page.getByLabel('Логин', { exact: true }).fill(username);
  await page.getByLabel('Пароль', { exact: true }).fill(value);
  await page
    .getByRole('button', { name: 'Войти в систему', exact: true })
    .click();
  await expect(page).not.toHaveURL(/\/login$/);
}
async function mutate(
  context: BrowserContext,
  path: string,
  data: object,
  key?: string,
  method = 'POST',
) {
  const token = (await (await context.request.get('/api/v1/auth/csrf')).json())
    .csrf_token;
  return context.request.fetch(`/api/v1${path}`, {
    method,
    headers: {
      Origin: origin,
      'X-CSRF-Token': token,
      ...(key ? { 'Idempotency-Key': key } : {}),
    },
    data,
  });
}
async function member(browser: Browser, context: BrowserContext, role: string) {
  const username = `warehouse_${unique()}`;
  const temporary = secret();
  expect(
    (
      await mutate(context, '/users', {
        username,
        display_name: 'Синтетический оператор склада',
        role,
        password: temporary,
      })
    ).status(),
  ).toBe(201);
  const session = await browser.newContext({ baseURL: origin });
  const page = await session.newPage();
  await login(page, username, temporary);
  expect(
    (
      await mutate(session, '/auth/password', {
        current_password: temporary,
        new_password: secret(),
      })
    ).status(),
  ).toBe(200);
  await page.goto('/inventory');
  return { session, page };
}
async function addReference(
  page: Page,
  name: string,
  fields: Record<string, string>,
  select?: Record<string, string>,
) {
  await page.getByRole('tab', { name, exact: true }).click();
  await page
    .getByRole('button', { name: 'Добавить запись', exact: true })
    .click();
  const dialog = page.getByRole('dialog');
  for (const [label, value] of Object.entries(fields))
    await dialog.getByLabel(label, { exact: true }).fill(value);
  for (const [label, value] of Object.entries(select ?? {}))
    await dialog
      .getByLabel(label, { exact: true })
      .selectOption({ label: value });
  await dialog.getByRole('button', { name: 'Сохранить запись' }).click();
  await expect(dialog).not.toBeVisible();
}
test('администратор и кладовщик: справочники → фото/совместимость → 10 → ошибка → неизвестный ответ 3 → отмена 10', async ({
  page,
  context,
  browser,
}) => {
  test.setTimeout(150000);
  const suffix = unique();
  const code = `E2E-${suffix.toUpperCase()}`;
  const department = `Синтетический отдел ${suffix}`;
  const recipient = `Синтетический получатель ${suffix}`;
  await login(page);
  await page.goto('/directory');
  await addReference(page, 'Подразделения', {
    Код: `DEP-${suffix}`,
    Название: department,
  });
  await addReference(
    page,
    'Сотрудники',
    { 'Табельный номер': `EMP-${suffix}`, 'ФИО получателя': recipient },
    { Подразделение: department },
  );
  const { session, page: operator } = await member(
    browser,
    context,
    'storekeeper',
  );
  try {
    await expect(
      operator.getByRole('link', { name: 'Справочники', exact: true }),
    ).toHaveCount(0);
    await operator.getByRole('link', { name: 'Справочники склада' }).click();
    const maker = `Расходники ${suffix}`,
      printerMaker = `Принтеры ${suffix}`;
    await addReference(operator, 'Производители', { Название: maker });
    await addReference(operator, 'Производители', { Название: printerMaker });
    await addReference(
      operator,
      'Модели принтеров',
      { 'Модель принтера': `Laser A ${suffix}` },
      { Производитель: printerMaker },
    );
    await addReference(
      operator,
      'Модели принтеров',
      { 'Модель принтера': `Laser B ${suffix}` },
      { Производитель: printerMaker },
    );
    await operator.getByRole('link', { name: 'К каталогу' }).click();
    await operator.getByRole('button', { name: 'Создать позицию' }).click();
    const dialog = operator.getByRole('dialog');
    const longModel = `Синтетический расходник ${suffix} ${'Длинноеназвание'.repeat(10)}`;
    await dialog.getByLabel('Внутренний код', { exact: true }).fill(code);
    await dialog
      .getByLabel('Категория', { exact: true })
      .selectOption({ label: 'Картриджи' });
    await dialog
      .getByLabel('Производитель', { exact: true })
      .selectOption({ label: maker });
    await dialog
      .getByLabel('Модель расходника', { exact: true })
      .fill(longModel);
    await dialog.getByLabel('Минимальный остаток', { exact: true }).fill('2');
    await dialog.getByRole('button', { name: 'Сохранить товар' }).click();
    await expect(operator).toHaveURL(/\/inventory\/items\/[a-f0-9-]+$/);
    const itemId = new URL(operator.url()).pathname.split('/').at(-1)!;
    await operator
      .getByRole('button', { name: 'Изменить совместимость' })
      .click();
    await operator
      .getByLabel(`${printerMaker} Laser A ${suffix}`, { exact: true })
      .check();
    await operator
      .getByLabel(`${printerMaker} Laser B ${suffix}`, { exact: true })
      .check();
    await operator
      .getByRole('button', { name: 'Сохранить совместимость' })
      .click();
    await expect(operator.getByRole('dialog')).not.toBeVisible();
    const compatibility = await (
      await session.request.get(
        `/api/v1/inventory/items/${itemId}/compatibilities`,
      )
    ).json();
    expect(compatibility.total).toBe(2);
    const png = Buffer.from(
      'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
      'base64',
    );
    await operator.getByLabel('Загрузить фото', { exact: true }).setInputFiles({
      name: 'synthetic.png',
      mimeType: 'image/png',
      buffer: png,
    });
    await operator
      .getByRole('button', { name: 'Сохранить фотографии', exact: true })
      .click();
    const photo = operator.getByRole('img', {
      name: 'Фотография позиции · главная',
      exact: true,
    });
    await expect(photo).toBeVisible();
    await expect
      .poll(() =>
        photo.evaluate((image: HTMLImageElement) => image.naturalWidth),
      )
      .toBeGreaterThan(0);
    const photoUrl = (await photo.getAttribute('src'))!;
    const anonymous = await browser.newContext({ baseURL: origin });
    try {
      expect((await anonymous.request.get(photoUrl)).status()).toBe(401);
    } finally {
      await anonymous.close();
    }
    await operator.setViewportSize({ width: 390, height: 844 });
    await expect
      .poll(() =>
        operator.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      )
      .toBe(true);
    await operator.setViewportSize({ width: 1440, height: 1000 });
    await operator.getByRole('link', { name: 'К каталогу' }).click();
    await operator
      .getByRole('link', { name: 'Поступление', exact: true })
      .click();
    await operator.getByLabel('Поиск позиций').fill(code);
    await operator
      .getByRole('button', { name: `Добавить в корзину ${code}` })
      .click();
    await operator.getByLabel(`Количество ${code}`, { exact: true }).fill('10');
    await operator
      .getByLabel('Назначение поступления')
      .selectOption('opening_balance');
    await operator
      .getByRole('button', { name: 'Проверить поступление' })
      .click();
    await operator
      .getByRole('button', { name: 'Подтвердить поступление', exact: true })
      .click();
    await expect(
      operator.getByText('Документ проведён.', { exact: true }),
    ).toBeVisible();
    expect(
      (
        await (
          await session.request.get(`/api/v1/inventory/items/${itemId}`)
        ).json()
      ).balance,
    ).toBe(10);
    await operator.getByRole('link', { name: 'Выдача', exact: true }).click();
    await operator.getByLabel('Поиск позиций').fill(code);
    await operator
      .getByRole('button', { name: `Добавить в корзину ${code}` })
      .click();
    await operator.getByLabel(`Количество ${code}`, { exact: true }).fill('11');
    await operator
      .getByLabel('Сотрудник-получатель')
      .selectOption({ label: `${recipient} · EMP-${suffix} · ${department}` });
    await operator.getByRole('button', { name: 'Проверить выдачу' }).click();
    await operator
      .getByRole('button', { name: 'Подтвердить выдачу', exact: true })
      .click();
    await expect(
      operator.getByText(/Доступно: 10 шт., запрошено: 11 шт./),
    ).toBeVisible();
    await expect(
      operator.getByLabel(`Количество ${code}`, { exact: true }),
    ).toHaveValue('11');
    await operator.getByLabel(`Количество ${code}`, { exact: true }).fill('3');
    let firstKey: string | undefined;
    let firstBody: string | null = null;
    let issueId = '';
    await operator.route(
      '**/api/v1/inventory/issues',
      async (route) => {
        if (route.request().method() !== 'POST') {
          await route.continue();
          return;
        }
        firstKey = route.request().headers()['idempotency-key'];
        firstBody = route.request().postData();
        const response = await route.fetch();
        expect(response.status()).toBe(201);
        issueId = (await response.json()).id;
        await route.abort('connectionfailed');
      },
      { times: 1 },
    );
    await operator.getByRole('button', { name: 'Проверить выдачу' }).click();
    await operator
      .getByRole('button', { name: 'Подтвердить выдачу', exact: true })
      .click();
    await expect(
      operator.getByText(/Результат операции пока неизвестен/),
    ).toBeVisible();
    await expect(
      operator.getByLabel(`Количество ${code}`, { exact: true }),
    ).toBeDisabled();
    const repeat = operator.waitForResponse(
      (response) =>
        response.url().endsWith('/api/v1/inventory/issues') &&
        response.request().method() === 'POST',
    );
    await operator.getByRole('button', { name: 'Повторить отправку' }).click();
    const replay = await repeat;
    expect(replay.status()).toBe(200);
    expect(replay.request().headers()['idempotency-key']).toBe(firstKey);
    expect(replay.request().postData()).toBe(firstBody);
    await expect(
      operator.getByText('Документ проведён.', { exact: true }),
    ).toBeVisible();
    expect(
      (
        await (
          await session.request.get(`/api/v1/inventory/items/${itemId}`)
        ).json()
      ).balance,
    ).toBe(7);
    await operator.goto(`/inventory/documents/${issueId}`);
    await operator
      .getByRole('button', { name: 'Отменить документ', exact: true })
      .click();
    await operator
      .getByLabel('Причина отмены', { exact: true })
      .fill('Синтетическая проверка ошибочной выдачи');
    await operator.getByRole('button', { name: 'Подтвердить отмену' }).click();
    await expect(operator.getByText(/Операция отменена/)).toBeVisible();
    const source = await (
      await session.request.get(`/api/v1/inventory/documents/${issueId}`)
    ).json();
    expect(source.is_cancelled).toBe(true);
    expect(source.reversal_id).toBeTruthy();
    expect(
      (
        await (
          await session.request.get(`/api/v1/inventory/items/${itemId}`)
        ).json()
      ).balance,
    ).toBe(10);
    const movements = await (
      await session.request.get(`/api/v1/inventory/items/${itemId}/movements`)
    ).json();
    expect(
      movements.items
        .map((movement: { delta: number }) => movement.delta)
        .sort((a: number, b: number) => a - b),
    ).toEqual([-3, 3, 10]);
    expect((await session.request.get(photoUrl)).status()).toBe(200);
    expect(
      await operator.evaluate(() => [
        localStorage.length,
        sessionStorage.length,
      ]),
    ).toEqual([0, 0]);
    await operator.getByRole('link', { name: /Документ отмены INV-/ }).click();
    await expect(
      operator.getByRole('link', { name: 'Исходный документ' }),
    ).toBeVisible();
    await expect(
      operator.getByRole('button', { name: 'Отменить документ', exact: true }),
    ).toHaveCount(0);
  } finally {
    await session.close();
  }
});

test('полный пользовательский путь: справочники в карточке → фото → 20 → черновик 5 → 15 → отказ 16 → история и Excel', async ({
  page,
  context,
  browser,
}) => {
  test.setTimeout(240000);
  await page.setViewportSize({ width: 1920, height: 1080 });
  const suffix = unique(),
    code = `FLOW-${suffix.toUpperCase()}`,
    maker = `Производитель ${suffix}`,
    category = `Категория ${suffix}`;
  const department = `Отдел ${suffix}`,
    recipient = `Получатель ${suffix}`;
  const png = Buffer.from(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
    'base64',
  );
  await login(page);
  await page.goto('/directory');
  await addReference(page, 'Подразделения', {
    Код: `FLOW-${suffix}`,
    Название: department,
  });
  await addReference(
    page,
    'Сотрудники',
    { 'Табельный номер': `FLOW-${suffix}`, 'ФИО получателя': recipient },
    { Подразделение: department },
  );
  await page.goto('/inventory');
  await page
    .getByRole('button', { name: 'Создать позицию', exact: true })
    .click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Внутренний код', { exact: true }).fill(code);
  await dialog
    .getByRole('button', { name: 'Новая категория', exact: true })
    .click();
  await dialog.getByLabel('Код новой категории').fill(`flow-${suffix}`);
  await dialog.getByLabel('Название новой категории').fill(category);
  await dialog
    .getByRole('button', { name: 'Сохранить категорию', exact: true })
    .click();
  await expect(dialog.getByLabel('Категория', { exact: true })).toHaveValue(
    /[a-f0-9-]{36}/,
  );
  await dialog
    .getByRole('button', { name: 'Новый производитель', exact: true })
    .click();
  await dialog.getByLabel('Название нового производителя').fill(maker);
  await dialog
    .getByRole('button', { name: 'Сохранить производителя', exact: true })
    .click();
  await expect(dialog.getByLabel('Производитель', { exact: true })).toHaveValue(
    /[a-f0-9-]{36}/,
  );
  await dialog.getByLabel('Модель расходника').fill(`Модель ${suffix}`);
  await dialog.getByLabel('Артикул', { exact: true }).fill(`ARTICLE-${suffix}`);
  await dialog
    .getByLabel('Описание', { exact: true })
    .fill('Синтетическая проверка полного складского пути');
  await dialog.getByLabel('Минимальный остаток').fill('16');
  await dialog.getByLabel('Загрузить фото', { exact: true }).setInputFiles([
    { name: 'first.png', mimeType: 'image/png', buffer: png },
    { name: 'second.png', mimeType: 'image/png', buffer: png },
  ]);
  await expect(dialog.getByRole('img', { name: /Предпросмотр/ })).toHaveCount(
    2,
  );
  await dialog
    .getByRole('button', { name: 'Сохранить товар', exact: true })
    .click();
  await expect(page).toHaveURL(/\/inventory\/items\/[a-f0-9-]+$/);
  const itemId = new URL(page.url()).pathname.split('/').at(-1)!;
  await expect(
    page.getByRole('img', { name: /Фотография позиции/ }),
  ).toHaveCount(2);
  const secondary = page.locator('figure').filter({
    has: page.getByRole('img', { name: 'Фотография позиции', exact: true }),
  });
  const secondPhotoUrl = await secondary.getByRole('img').getAttribute('src');
  await secondary.getByRole('button', { name: 'Сделать главным' }).click();
  await expect(
    page
      .locator('figure')
      .filter({ has: page.locator(`img[src="${secondPhotoUrl}"]`) })
      .getByRole('button', { name: 'Сделать главным' }),
  ).toBeDisabled();
  const nonPrimary = page.locator('figure').filter({
    has: page.getByRole('img', { name: 'Фотография позиции', exact: true }),
  });
  await nonPrimary.getByRole('button', { name: 'Убрать фото' }).click();
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Подтвердить', exact: true })
    .click();
  await expect(
    page.getByRole('img', { name: /Фотография позиции/ }),
  ).toHaveCount(1);
  const photoUrl = (await page
    .getByRole('img', { name: 'Фотография позиции · главная', exact: true })
    .getAttribute('src'))!;
  const anonymous = await browser.newContext({ baseURL: origin });
  try {
    expect((await anonymous.request.get(photoUrl)).status()).toBe(401);
  } finally {
    await anonymous.close();
  }
  await page.goto('/inventory/catalogs');
  await addReference(
    page,
    'Модели принтеров',
    { 'Модель принтера': `Совместимая модель ${suffix}` },
    { Производитель: maker },
  );
  await page.goto(`/inventory/items/${itemId}`);
  await page.getByRole('button', { name: 'Изменить совместимость' }).click();
  await page
    .getByLabel(`${maker} Совместимая модель ${suffix}`, { exact: true })
    .check();
  await page.getByRole('button', { name: 'Сохранить совместимость' }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await page
    .getByRole('button', { name: 'Редактировать', exact: true })
    .click();
  await page.screenshot({ path: visualPath('item-edit-desktop') });
  await page
    .getByLabel('Описание', { exact: true })
    .fill(`Изменённая карточка ${suffix}`);
  await page.getByRole('button', { name: 'Сохранить товар' }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  await page.reload();
  await expect(
    page.getByText(`Изменённая карточка ${suffix}`, { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(`${maker} Совместимая модель ${suffix}`, { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('img', {
      name: 'Фотография позиции · главная',
      exact: true,
    }),
  ).toHaveAttribute('src', photoUrl);
  const current = await (
    await context.request.get(`/api/v1/inventory/items/${itemId}`)
  ).json();
  await page
    .getByRole('button', { name: 'Редактировать', exact: true })
    .click();
  await page
    .getByLabel('Описание', { exact: true })
    .fill(`Несохранённая правка ${suffix}`);
  const concurrent = await mutate(
    context,
    `/inventory/items/${itemId}`,
    { version: current.version, description: `Параллельная правка ${suffix}` },
    undefined,
    'PATCH',
  );
  expect(concurrent.status()).toBe(200);
  const staleResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/inventory/items/${itemId}`) &&
      response.request().method() === 'PATCH',
  );
  await page.getByRole('button', { name: 'Сохранить товар' }).click();
  expect((await staleResponse).status()).toBe(409);
  await expect(page.getByLabel('Описание', { exact: true })).toHaveValue(
    `Несохранённая правка ${suffix}`,
  );
  await expect(page.getByRole('dialog').getByRole('alert')).toBeVisible();
  await page.reload();
  await expect(
    page.getByText(`Параллельная правка ${suffix}`, { exact: true }),
  ).toBeVisible();
  await page.goto('/inventory/receipt');
  await page.getByLabel('Поиск позиций').fill(code);
  await page
    .getByRole('button', { name: `Добавить в корзину ${code}` })
    .click();
  await page.getByLabel(`Количество ${code}`, { exact: true }).fill('20');
  await page
    .getByLabel('Поставщик', { exact: true })
    .fill(`Поставщик ${suffix}`);
  await page.getByLabel('Внешний номер', { exact: true }).fill(`IN-${suffix}`);
  const date = await page
    .getByLabel('Дата документа', { exact: true })
    .inputValue();
  await page.getByRole('button', { name: 'Проверить поступление' }).click();
  const receiptResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith('/inventory/receipts') &&
      response.request().method() === 'POST',
  );
  await page
    .getByRole('button', { name: 'Подтвердить поступление', exact: true })
    .click();
  await expect(
    page.getByText('Документ проведён.', { exact: true }),
  ).toBeVisible();
  const received = await (await receiptResponse).json();
  expect(received.supplier_name).toBe(`Поставщик ${suffix}`);
  expect(received.external_number).toBe(`IN-${suffix}`);
  const balance = async () =>
    (
      await (
        await context.request.get(`/api/v1/inventory/items/${itemId}`)
      ).json()
    ).balance;
  expect(await balance()).toBe(20);
  await page.goto('/inventory');
  await page.getByLabel('Поиск позиций').fill(code);
  await expect(page.getByLabel(`Остаток ${code}`, { exact: true })).toHaveText(
    '20 шт.',
  );
  await page.goto('/issues');
  await page.getByLabel('Поиск позиций').fill(code);
  await page
    .getByRole('button', { name: `Добавить в корзину ${code}` })
    .click();
  await page.getByLabel(`Количество ${code}`, { exact: true }).fill('5');
  await page
    .getByLabel('Сотрудник-получатель')
    .selectOption({ label: `${recipient} · FLOW-${suffix} · ${department}` });
  await expect(page.getByLabel('Подразделение', { exact: true })).toHaveValue(
    department,
  );
  await page.getByLabel('Кабинет', { exact: true }).fill('301');
  await page
    .getByLabel('Комментарий', { exact: true })
    .fill(`Черновик ${suffix}`);
  await page
    .getByRole('button', { name: 'Сохранить черновик', exact: true })
    .click();
  await expect(
    page.getByText('Черновик сохранён на сервере.', { exact: true }),
  ).toBeVisible();
  expect(await balance()).toBe(20);
  const drafts = await (
    await context.request.get('/api/v1/inventory/drafts')
  ).json();
  const draft = drafts.items.find(
    (value: { payload: { comment: string } }) =>
      value.payload.comment === `Черновик ${suffix}`,
  );
  expect(draft).toBeTruthy();
  await page.reload();
  await page.goto('/inventory/drafts');
  const draftRow = page
    .getByRole('listitem')
    .filter({ hasText: `Черновик ${suffix}` });
  await draftRow.getByRole('button', { name: 'Открыть черновик' }).click();
  await page
    .getByRole('dialog')
    .getByRole('button', { name: 'Подтвердить', exact: true })
    .click();
  await expect(
    page.getByLabel(`Количество ${code}`, { exact: true }),
  ).toHaveValue('5');
  await expect(page.getByLabel('Кабинет', { exact: true })).toHaveValue('301');
  await page.getByRole('button', { name: 'Проверить выдачу' }).click();
  await page
    .getByRole('button', { name: 'Подтвердить выдачу', exact: true })
    .click();
  await expect(
    page.getByText('Документ проведён.', { exact: true }),
  ).toBeVisible();
  expect(await balance()).toBe(15);
  const posted = await (
    await context.request.get(`/api/v1/inventory/drafts/${draft.id}`)
  ).json();
  expect(posted.status).toBe('posted');
  const issued = await (
    await context.request.get(
      `/api/v1/inventory/documents/${posted.posted_document_id}`,
    )
  ).json();
  expect(issued.recipient_room).toBe('301');
  await page.getByLabel('Поиск позиций').fill(code);
  await page
    .getByRole('button', { name: `Добавить в корзину ${code}` })
    .click();
  await page.getByLabel(`Количество ${code}`, { exact: true }).fill('16');
  await page
    .getByLabel('Сотрудник-получатель')
    .selectOption({ label: `${recipient} · FLOW-${suffix} · ${department}` });
  await page.getByRole('button', { name: 'Проверить выдачу' }).click();
  await page
    .getByRole('button', { name: 'Подтвердить выдачу', exact: true })
    .click();
  await expect(
    page.getByText(/Доступно: 15 шт., запрошено: 16 шт./),
  ).toBeVisible();
  await expect(
    page.getByLabel(`Количество ${code}`, { exact: true }),
  ).toHaveValue('16');
  expect(await balance()).toBe(15);
  await page.goto('/inventory');
  await page.getByLabel('Поиск позиций').fill(code);
  await page
    .getByLabel('Категория', { exact: true })
    .selectOption({ label: category });
  await page
    .getByLabel('Производитель', { exact: true })
    .selectOption({ label: maker });
  await page.getByLabel('Ниже минимального остатка').check();
  await expect(page.getByLabel(`Остаток ${code}`, { exact: true })).toHaveText(
    '15 шт.',
  );
  await page.reload();
  await page.getByLabel('Поиск позиций').fill(code);
  await expect(page.getByLabel(`Остаток ${code}`, { exact: true })).toHaveText(
    '15 шт.',
  );
  const balances = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Скачать остатки в Excel' }).click();
  expect((await balances).suggestedFilename()).toBe('balances.xlsx');
  await page.goto('/history');
  await page
    .getByLabel('Тип документа', { exact: true })
    .selectOption('receipt');
  await page.getByLabel('Дата с', { exact: true }).fill(date);
  await page.getByLabel('Дата по', { exact: true }).fill(date);
  await expect(
    page.getByRole('link', { name: received.number, exact: true }),
  ).toBeVisible();
  await page.getByLabel('Тип документа', { exact: true }).selectOption('issue');
  await page
    .getByLabel('Получатель', { exact: true })
    .selectOption(issued.recipient_employee_id);
  await page.getByLabel('Дата с', { exact: true }).fill(date);
  await page.getByLabel('Дата по', { exact: true }).fill(date);
  await page.getByLabel('Только мои операции').check();
  await expect(
    page.getByRole('link', { name: issued.number, exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole('link', { name: issued.number, exact: true }),
  ).toBeVisible();
  await page.goto('/reports');
  await page.getByLabel('Позиция для отчёта').selectOption(itemId);
  await page.getByLabel('Тип движения').selectOption('issue');
  await page
    .getByLabel('Получатель отчёта')
    .selectOption(issued.recipient_employee_id);
  const download = page.waitForEvent('download');
  const response = page.waitForResponse((value) =>
    value.url().includes('/exports/movements.xlsx'),
  );
  await page.getByRole('button', { name: 'Скачать движения в Excel' }).click();
  expect((await response).status()).toBe(200);
  expect((await download).suggestedFilename()).toBe('movements.xlsx');
  const movements = await (
    await context.request.get(`/api/v1/inventory/items/${itemId}/movements`)
  ).json();
  expect(
    movements.items
      .map((value: { delta: number }) => value.delta)
      .sort((a: number, b: number) => a - b),
  ).toEqual([-5, 20]);
  expect(
    await page.evaluate(() => [localStorage.length, sessionStorage.length]),
  ).toEqual([0, 0]);
});

for (const role of ['manager', 'it_specialist', 'storekeeper']) {
  test(`UI и прямые складские HTTP-права: ${role}`, async ({
    page,
    context,
    browser,
  }) => {
    test.setTimeout(60000);
    await login(page);
    const { session, page: operator } = await member(browser, context, role);
    try {
      const manage = role === 'storekeeper';
      const issue = role !== 'manager';
      await expect(
        operator.getByRole('heading', { name: 'Склад', exact: true }),
      ).toBeVisible();
      await expect(
        operator.getByRole('button', { name: 'Создать позицию', exact: true }),
      ).toHaveCount(manage ? 1 : 0);
      await expect(
        operator.getByRole('link', { name: 'Поступление', exact: true }),
      ).toHaveCount(manage ? 1 : 0);
      await expect(
        operator.getByRole('link', { name: 'Выдача', exact: true }),
      ).toHaveCount(issue ? 1 : 0);
      await operator
        .getByRole('link', { name: 'Документы', exact: true })
        .click();
      await expect(
        operator.getByRole('heading', { name: 'Складские документы' }),
      ).toBeVisible();
      expect(
        (await session.request.get('/api/v1/inventory/documents')).status(),
      ).toBe(200);
      const receipt = await mutate(
        session,
        '/inventory/receipts',
        {},
        randomUUID(),
      );
      expect(receipt.status()).toBe(manage ? 422 : 403);
      const issuance = await mutate(
        session,
        '/inventory/issues',
        {},
        randomUUID(),
      );
      expect(issuance.status()).toBe(issue ? 422 : 403);
      expect(
        (
          await mutate(session, '/directory/departments', {
            code: `NO-${unique()}`,
            name: 'Запрещено',
          })
        ).status(),
      ).toBe(403);
      await operator.goto('/inventory/receipt');
      await expect(
        operator.getByRole('heading', {
          name: manage ? 'Поступление' : 'Недостаточно прав',
          exact: true,
        }),
      ).toBeVisible();
    } finally {
      await session.close();
    }
  });
}

test('пустой поиск и ошибка API с повтором', async ({ page }) => {
  await login(page);
  await page.goto('/inventory');
  await page.getByLabel('Поиск позиций').fill(`absent-${unique()}`);
  await expect(
    page.getByText('Позиции не найдены', { exact: true }),
  ).toBeVisible();
  await page.route('**/api/v1/inventory/items?**', (route) =>
    route.fulfill({
      status: 503,
      contentType: 'application/json',
      body: JSON.stringify({
        detail: {
          code: 'unavailable',
          message: 'Тестовая недоступность склада',
        },
      }),
    }),
  );
  await page.getByLabel('Поиск позиций').fill('network-check');
  await expect(
    page.getByText('Тестовая недоступность склада', { exact: true }),
  ).toBeVisible();
  await page.unroute('**/api/v1/inventory/items?**');
  await page.getByRole('button', { name: 'Повторить', exact: true }).click();
  await expect(
    page.getByText('Позиции не найдены', { exact: true }),
  ).toBeVisible();
});

test('компактная карточка: 980px, вложенные диалоги, фокус и мобильный footer', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await login(page);
  await page.goto('/');
  await expect(
    page.getByRole('heading', { name: 'Добро пожаловать!' }),
  ).toBeVisible();
  await page.screenshot({ path: visualPath('dashboard-desktop') });
  await page.goto('/inventory');
  const trigger = page.getByRole('button', {
    name: 'Создать позицию',
    exact: true,
  });
  await expect(trigger).toBeVisible();
  await page.screenshot({ path: visualPath('catalog-desktop') });
  await trigger.click();
  const form = page.getByRole('dialog', {
    name: 'Создать позицию',
    exact: true,
  });
  await expect(form).toBeVisible();
  expect((await form.boundingBox())!.width).toBe(980);
  await form.getByLabel('Внутренний код', { exact: true }).fill('FOCUS-CHECK');
  await form
    .getByLabel('Модель расходника')
    .fill('Проверка компактной карточки');
  await page.screenshot({ path: visualPath('item-create-desktop') });
  const nestedTrigger = form.getByRole('button', {
    name: 'Новая категория',
    exact: true,
  });
  await nestedTrigger.click();
  const nested = page.getByRole('dialog', {
    name: 'Новая категория',
    exact: true,
  });
  await nested.getByLabel('Код новой категории').fill('keyboard-check');
  await page.screenshot({ path: visualPath('item-nested-desktop') });
  for (let index = 0; index < 6; index++) {
    await page.keyboard.press('Tab');
    expect(
      await nested.evaluate((element) =>
        element.contains(document.activeElement),
      ),
    ).toBe(true);
  }
  await page.keyboard.press('Escape');
  await expect(nested).not.toBeVisible();
  await expect(form).toBeVisible();
  await expect(nestedTrigger).toBeFocused();
  await expect(form.getByLabel('Внутренний код', { exact: true })).toHaveValue(
    'FOCUS-CHECK',
  );
  await page.keyboard.press('Escape');
  await expect(form).not.toBeVisible();
  await expect(trigger).toBeFocused();
  await page.setViewportSize({ width: 390, height: 844 });
  await trigger.click();
  await expect(form).toBeVisible();
  const save = form.getByRole('button', {
    name: 'Сохранить товар',
    exact: true,
  });
  const footerBefore = (await save.boundingBox())!;
  expect(footerBefore.y + footerBefore.height).toBeLessThan(844);
  expect(
    await form.evaluate(
      (element) => element.scrollWidth <= element.clientWidth,
    ),
  ).toBe(true);
  await form.locator('.item-form-scroll').evaluate((element) => {
    element.scrollTop = element.scrollHeight;
  });
  expect((await save.boundingBox())!.y).toBe(footerBefore.y);
  await page.screenshot({ path: visualPath('item-create-mobile') });
  await form.getByRole('button', { name: 'Отмена', exact: true }).click();
  await expect(trigger).toBeFocused();
  for (const path of [
    '/',
    '/inventory',
    '/inventory/receipt',
    '/inventory/drafts',
    '/history',
    '/reports',
  ]) {
    await page.goto(path);
    await expect(page.locator('main h1')).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  }
  await page.goto('/');
  await page.screenshot({ path: visualPath('dashboard-mobile') });
});
