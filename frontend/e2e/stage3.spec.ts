import { randomBytes, randomUUID } from 'node:crypto';
import { test, expect, type Page, type BrowserContext, type Browser } from '@playwright/test';

const origin = new URL(process.env.E2E_BASE_URL!).origin;
const admin = process.env.E2E_ADMIN_USERNAME ?? 'acceptance_admin';
const password = process.env.E2E_ADMIN_PASSWORD!;
const unique = () => randomBytes(5).toString('hex');
const secret = () => `Synthetic-${randomBytes(15).toString('hex')}`;
async function login(page: Page, username = admin, value = password) {
  await page.goto('/login');
  await page.getByLabel('Логин', { exact: true }).fill(username);
  await page.getByLabel('Пароль', { exact: true }).fill(value);
  await page.getByRole('button', { name: 'Войти в систему', exact: true }).click();
  await expect(page).not.toHaveURL(/\/login$/);
}
async function mutate(context: BrowserContext, path: string, data: object, key?:string) {
  const token = (await (await context.request.get('/api/v1/auth/csrf')).json()).csrf_token;
  return context.request.post(`/api/v1${path}`, { headers: { Origin: origin, 'X-CSRF-Token': token, ...(key?{'Idempotency-Key':key}:{}) }, data });
}
async function member(browser: Browser, context: BrowserContext, role: string) {
  const username = `warehouse_${unique()}`; const temporary = secret();
  expect((await mutate(context, '/users', { username, display_name: 'Синтетический оператор склада', role, password: temporary })).status()).toBe(201);
  const session = await browser.newContext({ baseURL: origin }); const page = await session.newPage();
  await login(page, username, temporary);
  expect((await mutate(session, '/auth/password', { current_password: temporary, new_password: secret() })).status()).toBe(200);
  await page.goto('/inventory');
  return { session, page };
}
async function addReference(page:Page, name:string, fields:Record<string,string>, select?:Record<string,string>) {
  await page.getByRole('tab', {name,exact:true}).click();
  await page.getByRole('button',{name:'Добавить запись',exact:true}).click();
  const dialog=page.getByRole('dialog');
  for(const [label,value] of Object.entries(fields)) await dialog.getByLabel(label,{exact:true}).fill(value);
  for(const [label,value] of Object.entries(select??{})) await dialog.getByLabel(label,{exact:true}).selectOption({label:value});
  await dialog.getByRole('button',{name:'Сохранить запись'}).click();
  await expect(dialog).not.toBeVisible();
}
test('администратор и кладовщик: справочники → фото/совместимость → 10 → ошибка → неизвестный ответ 3 → отмена 10', async({page,context,browser})=>{
  test.setTimeout(150000);
  const suffix=unique();const code=`E2E-${suffix.toUpperCase()}`;const department=`Синтетический отдел ${suffix}`;const recipient=`Синтетический получатель ${suffix}`;
  await login(page);
  await page.goto('/directory');
  await addReference(page,'Подразделения',{'Код':`DEP-${suffix}`,'Название':department});
  await addReference(page,'Сотрудники',{'Табельный номер':`EMP-${suffix}`,'ФИО получателя':recipient},{'Подразделение':department});
  const {session,page:operator}=await member(browser,context,'storekeeper');
  try {
    await expect(operator.getByRole('link',{name:'Справочники',exact:true})).toHaveCount(0);
    await operator.getByRole('link',{name:'Справочники склада'}).click();
    const maker=`Расходники ${suffix}`,printerMaker=`Принтеры ${suffix}`;
    await addReference(operator,'Производители',{'Название':maker});
    await addReference(operator,'Производители',{'Название':printerMaker});
    await addReference(operator,'Модели принтеров',{'Модель принтера':`Laser A ${suffix}`},{'Производитель':printerMaker});
    await addReference(operator,'Модели принтеров',{'Модель принтера':`Laser B ${suffix}`},{'Производитель':printerMaker});
    await operator.getByRole('link',{name:'К каталогу'}).click();
    await operator.getByRole('button',{name:'Создать позицию'}).click();
    const dialog=operator.getByRole('dialog');
    const longModel=`Синтетический расходник ${suffix} ${'Длинноеназвание'.repeat(10)}`;
    await dialog.getByLabel('Внутренний код',{exact:true}).fill(code);
    await dialog.getByLabel('Категория',{exact:true}).selectOption({label:'Картриджи'});
    await dialog.getByLabel('Производитель',{exact:true}).selectOption({label:maker});
    await dialog.getByLabel('Модель расходника',{exact:true}).fill(longModel);
    await dialog.getByLabel('Минимальный остаток',{exact:true}).fill('2');
    await dialog.getByRole('button',{name:'Сохранить позицию'}).click();
    await expect(operator).toHaveURL(/\/inventory\/items\/[a-f0-9-]+$/);
    const itemId=new URL(operator.url()).pathname.split('/').at(-1)!;
    await operator.getByRole('button',{name:'Изменить совместимость'}).click();
    await operator.getByLabel(`${printerMaker} Laser A ${suffix}`,{exact:true}).check();
    await operator.getByLabel(`${printerMaker} Laser B ${suffix}`,{exact:true}).check();
    await operator.getByRole('button',{name:'Сохранить совместимость'}).click();
    await expect(operator.getByRole('dialog')).not.toBeVisible();
    const compatibility=await (await session.request.get(`/api/v1/inventory/items/${itemId}/compatibilities`)).json();
    expect(compatibility.total).toBe(2);
    const png=Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=','base64');
    await operator.getByLabel('Загрузить фото',{exact:true}).setInputFiles({name:'synthetic.png',mimeType:'image/png',buffer:png});
    const photo=operator.getByRole('img',{name:'Фотография позиции · главная',exact:true});
    await expect(photo).toBeVisible();
    await expect.poll(()=>photo.evaluate((image:HTMLImageElement)=>image.naturalWidth)).toBeGreaterThan(0);
    const photoUrl=(await photo.getAttribute('src'))!;
    const anonymous=await browser.newContext({baseURL:origin});
    try {expect((await anonymous.request.get(photoUrl)).status()).toBe(401);} finally {await anonymous.close();}
    await operator.setViewportSize({width:390,height:844});
    expect(await operator.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
    await operator.setViewportSize({width:1440,height:1000});
    await operator.getByRole('link',{name:'К каталогу'}).click();
    await operator.getByRole('link',{name:'Поступление',exact:true}).click();
    await operator.getByLabel('Поиск позиций').fill(code);
    await operator.getByRole('button',{name:`Добавить в корзину ${code}`}).click();
    await operator.getByLabel(`Количество ${code}`,{exact:true}).fill('10');
    await operator.getByLabel('Назначение поступления').selectOption('opening_balance');
    await operator.getByRole('button',{name:'Проверить поступление'}).click();
    await operator.getByRole('button',{name:'Подтвердить поступление',exact:true}).click();
    await expect(operator.getByText('Документ проведён.',{exact:true})).toBeVisible();
    expect((await (await session.request.get(`/api/v1/inventory/items/${itemId}`)).json()).balance).toBe(10);
    await operator.getByRole('link',{name:'Выдача',exact:true}).click();
    await operator.getByLabel('Поиск позиций').fill(code);
    await operator.getByRole('button',{name:`Добавить в корзину ${code}`}).click();
    await operator.getByLabel(`Количество ${code}`,{exact:true}).fill('11');
    await operator.getByLabel('Сотрудник-получатель').selectOption({label:`${recipient} · EMP-${suffix} · ${department}`});
    await operator.getByRole('button',{name:'Проверить выдачу'}).click();
    await operator.getByRole('button',{name:'Подтвердить выдачу',exact:true}).click();
    await expect(operator.getByText(/Доступно: 10 шт., запрошено: 11 шт./)).toBeVisible();
    await expect(operator.getByLabel(`Количество ${code}`,{exact:true})).toHaveValue('11');
    await operator.getByLabel(`Количество ${code}`,{exact:true}).fill('3');
    let firstKey:string|undefined;let firstBody:string|null=null;let issueId='';
    await operator.route('**/api/v1/inventory/issues',async route=>{
      if(route.request().method()!=='POST'){await route.continue();return;}
      firstKey=route.request().headers()['idempotency-key'];firstBody=route.request().postData();
      const response=await route.fetch();expect(response.status()).toBe(201);issueId=(await response.json()).id;
      await route.abort('connectionfailed');
    },{times:1});
    await operator.getByRole('button',{name:'Проверить выдачу'}).click();
    await operator.getByRole('button',{name:'Подтвердить выдачу',exact:true}).click();
    await expect(operator.getByText(/Результат операции пока неизвестен/)).toBeVisible();
    await expect(operator.getByLabel(`Количество ${code}`,{exact:true})).toBeDisabled();
    const repeat=operator.waitForResponse(response=>response.url().endsWith('/api/v1/inventory/issues')&&response.request().method()==='POST');
    await operator.getByRole('button',{name:'Повторить отправку'}).click();
    const replay=await repeat;expect(replay.status()).toBe(200);expect(replay.request().headers()['idempotency-key']).toBe(firstKey);expect(replay.request().postData()).toBe(firstBody);
    await expect(operator.getByText('Документ проведён.',{exact:true})).toBeVisible();
    expect((await (await session.request.get(`/api/v1/inventory/items/${itemId}`)).json()).balance).toBe(7);
    await operator.goto(`/inventory/documents/${issueId}`);
    await operator.getByRole('button',{name:'Отменить документ',exact:true}).click();
    await operator.getByLabel('Причина отмены',{exact:true}).fill('Синтетическая проверка ошибочной выдачи');
    await operator.getByRole('button',{name:'Подтвердить отмену'}).click();
    await expect(operator.getByText(/Операция отменена/)).toBeVisible();
    const source=await (await session.request.get(`/api/v1/inventory/documents/${issueId}`)).json();
    expect(source.is_cancelled).toBe(true);expect(source.reversal_id).toBeTruthy();
    expect((await (await session.request.get(`/api/v1/inventory/items/${itemId}`)).json()).balance).toBe(10);
    const movements=await (await session.request.get(`/api/v1/inventory/items/${itemId}/movements`)).json();
    expect(movements.items.map((movement:{delta:number})=>movement.delta).sort((a:number,b:number)=>a-b)).toEqual([-3,3,10]);
    expect((await session.request.get(photoUrl)).status()).toBe(200);
    expect(await operator.evaluate(()=>[localStorage.length,sessionStorage.length])).toEqual([0,0]);
    await operator.getByRole('link',{name:/Документ отмены INV-/}).click();
    await expect(operator.getByRole('link',{name:'Исходный документ'})).toBeVisible();
    await expect(operator.getByRole('button',{name:'Отменить документ',exact:true})).toHaveCount(0);
  }finally{await session.close();}
});

for(const role of ['manager','it_specialist','storekeeper']) {
  test(`UI и прямые складские HTTP-права: ${role}`,async({page,context,browser})=>{
    test.setTimeout(60000);await login(page);const {session,page:operator}=await member(browser,context,role);
    try {
      const manage=role==='storekeeper';const issue=role!=='manager';
      await expect(operator.getByRole('heading',{name:'Склад',exact:true})).toBeVisible();
      await expect(operator.getByRole('button',{name:'Создать позицию',exact:true})).toHaveCount(manage?1:0);
      await expect(operator.getByRole('link',{name:'Поступление',exact:true})).toHaveCount(manage?1:0);
      await expect(operator.getByRole('link',{name:'Выдача',exact:true})).toHaveCount(issue?1:0);
      await operator.getByRole('link',{name:'Документы',exact:true}).click();
      await expect(operator.getByRole('heading',{name:'Складские документы'})).toBeVisible();
      expect((await session.request.get('/api/v1/inventory/documents')).status()).toBe(200);
      const receipt=await mutate(session,'/inventory/receipts',{},randomUUID());expect(receipt.status()).toBe(manage?422:403);
      const issuance=await mutate(session,'/inventory/issues',{},randomUUID());expect(issuance.status()).toBe(issue?422:403);
      expect((await mutate(session,'/directory/departments',{code:`NO-${unique()}`,name:'Запрещено'})).status()).toBe(403);
      await operator.goto('/inventory/receipt');
      await expect(operator.getByRole('heading',{name:manage?'Поступление':'Недостаточно прав',exact:true})).toBeVisible();
    }finally{await session.close();}
  });
}

test('пустой поиск и ошибка API с повтором',async({page})=>{
  await login(page);await page.goto('/inventory');await page.getByLabel('Поиск позиций').fill(`absent-${unique()}`);
  await expect(page.getByText('Позиции не найдены',{exact:true})).toBeVisible();
  await page.route('**/api/v1/inventory/items?**',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:{code:'unavailable',message:'Тестовая недоступность склада'}})}));
  await page.getByLabel('Поиск позиций').fill('network-check');
  await expect(page.getByText('Тестовая недоступность склада',{exact:true})).toBeVisible();
  await page.unroute('**/api/v1/inventory/items?**');
  await page.getByRole('button',{name:'Повторить',exact:true}).click();
  await expect(page.getByText('Позиции не найдены',{exact:true})).toBeVisible();
});
