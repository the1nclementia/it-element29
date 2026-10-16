const button = document.querySelector('#refresh');

async function probe(id, path, success, failure) {
  const target = document.getElementById(id);
  target.textContent = 'Проверка…';
  target.className = '';
  try {
    const response = await fetch(path, { cache: 'no-store', signal: AbortSignal.timeout(10000) });
    const body = await response.json();
    const ok = response.ok && body.status === 'ok';
    target.textContent = ok ? success : failure;
    target.className = ok ? 'ok' : 'error';
  } catch {
    target.textContent = 'Нет связи с сервером';
    target.className = 'error';
  }
}

async function refresh() {
  button.disabled = true;
  await Promise.all([
    probe('live', '/api/v1/health/live', 'Доступен', 'Недоступен'),
    probe('ready', '/api/v1/health/ready', 'Готовы', 'Не готовы'),
  ]);
  document.querySelector('#checked').textContent = `Проверено: ${new Date().toLocaleString('ru-RU')}`;
  button.disabled = false;
}

button.addEventListener('click', refresh);
refresh();
