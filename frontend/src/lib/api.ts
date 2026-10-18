const prefix = '/api/v1';
let csrfToken: string | null = null;
let csrfRequest: Promise<void> | null = null;
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}
export function setCsrf(token: string | null) {
  csrfToken = token;
}
export async function refreshCsrf() {
  if (!csrfRequest)
    csrfRequest = request<{ csrf_token: string }>('/auth/csrf', {
      anonymous: true,
    })
      .then((result) => {
        csrfToken = result.csrf_token;
      })
      .finally(() => {
        csrfRequest = null;
      });
  await csrfRequest;
}
type Options = Omit<RequestInit, 'body'> & {
  body?: unknown;
  anonymous?: boolean;
};
export async function request<T>(
  path: string,
  { body, anonymous = false, ...options }: Options = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  if (body !== undefined) headers.set('Content-Type', 'application/json');
  if (options.method && !['GET', 'HEAD'].includes(options.method)) {
    if (!csrfToken) await refreshCsrf();
    headers.set('X-CSRF-Token', csrfToken!);
  }
  let response: Response;
  try {
    response = await fetch(`${prefix}${path}`, {
      ...options,
      headers,
      credentials: 'same-origin',
      cache: 'no-store',
      ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
    });
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw error;
    throw new ApiError(
      0,
      'network',
      'Не удалось связаться с сервером. Проверьте подключение и повторите попытку.',
    );
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const detail = payload?.detail;
    const code =
      typeof detail?.code === 'string' ? detail.code : 'request_failed';
    const message =
      typeof detail?.message === 'string'
        ? detail.message
        : response.status === 422
          ? 'Проверьте заполнение полей.'
          : response.status === 403
            ? 'Недостаточно прав для выполнения действия.'
            : 'Не удалось выполнить запрос. Повторите попытку.';
    if (response.status === 401 && !anonymous) {
      csrfToken = null;
      window.dispatchEvent(new Event('auth:expired'));
    }
    if (response.status === 403 && code === 'password_change_required')
      window.dispatchEvent(new Event('auth:password-required'));
    if (code.includes('csrf')) csrfToken = null;
    const retryAfter = response.headers.get('Retry-After');
    throw new ApiError(
      response.status,
      code,
      response.status === 429 && retryAfter && /^\d+$/.test(retryAfter)
        ? `${message} Повторите через ${retryAfter} сек.`
        : message,
    );
  }
  return response.status === 204
    ? (undefined as T)
    : ((await response.json()) as T);
}
