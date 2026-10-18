import { useState, type FormEvent } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Ban,
  ChevronLeft,
  ChevronRight,
  KeyRound,
  Plus,
  Search,
  ShieldCheck,
  UserCheck,
  UsersRound,
} from 'lucide-react';
import { useAuth } from '../auth';
import { request } from '../lib/api';
import type { Role, User } from '../types';
import {
  ConfirmDialog,
  DataTable,
  EmptyState,
  ErrorState,
  Field,
  LoadingState,
  Notice,
  PageHeader,
  StatusBadge,
} from '../components/common';
import { Button } from '../components/ui/button';
import { Input, Select } from '../components/ui/input';
type Action =
  { kind: 'create' } | { kind: 'role' | 'block' | 'reset'; user: User };
export function Users() {
  const { user: actor } = useAuth();
  const client = useQueryClient();
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(0);
  const [action, setAction] = useState<Action | null>(null);
  const [message, setMessage] = useState('');
  const users = useQuery({
    queryKey: ['users', query, page],
    queryFn: ({ signal }) =>
      request<{ items: User[]; total: number }>(
        `/users?offset=${page * 20}&limit=20&q=${encodeURIComponent(query)}`,
        { signal },
      ),
  });
  const roles = useQuery({
    queryKey: ['roles'],
    queryFn: ({ signal }) => request<{ items: Role[] }>('/roles', { signal }),
  });
  return (
    <>
      <PageHeader
        title="Пользователи"
        description="Управляйте учётными записями и доступом к системе"
      >
        <Button
          disabled={!roles.data}
          onClick={() => {
            setMessage('');
            setAction({ kind: 'create' });
          }}
        >
          <Plus />
          Добавить пользователя
        </Button>
      </PageHeader>
      {message && (
        <div className="mb-5">
          <Notice success>{message}</Notice>
        </div>
      )}
      {roles.error && (
        <div className="mb-5">
          <ErrorState
            error={roles.error}
            onRetry={() => void roles.refetch()}
          />
        </div>
      )}
      <section className="overflow-hidden rounded-xl border border-border bg-white">
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border p-5">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold">Учётные записи</h2>
            {users.data && (
              <span className="rounded-md bg-slate-100 px-2 py-0.5 text-xs text-muted">
                {users.data.total}
              </span>
            )}
          </div>
          <form
            className="flex w-full gap-2 sm:w-auto"
            onSubmit={(e) => {
              e.preventDefault();
              setQuery(search.trim());
              setPage(0);
            }}
          >
            <div className="relative flex-1">
              <Search className="absolute left-3 top-3 size-4 text-slate-400" />
              <Input
                className="h-10 pl-9 sm:w-64"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                maxLength={160}
                aria-label="Поиск пользователей"
                placeholder="Имя или логин"
              />
            </div>
            <Button variant="outline" type="submit">
              Найти
            </Button>
          </form>
        </div>
        {users.isPending ? (
          <LoadingState />
        ) : users.error ? (
          <ErrorState
            error={users.error}
            onRetry={() => void users.refetch()}
          />
        ) : users.data.items.length === 0 ? (
          <EmptyState
            icon={UsersRound}
            title="Пользователи не найдены"
            description={
              query
                ? 'Попробуйте изменить поисковый запрос.'
                : 'Добавьте первую учётную запись сотрудника.'
            }
          />
        ) : (
          <DataTable
            rows={users.data.items}
            columns={[
              {
                key: 'name',
                label: 'Сотрудник',
                render: (user) => (
                  <div className="flex items-center gap-3">
                    <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-slate-100 text-xs font-semibold text-muted">
                      {user.display_name.slice(0, 2).toUpperCase()}
                    </span>
                    <div>
                      <p className="whitespace-nowrap font-medium">
                        {user.display_name}
                        {user.id === actor?.id && (
                          <span className="ml-2 text-xs font-normal text-muted">
                            Вы
                          </span>
                        )}
                      </p>
                      <p className="mt-1 text-xs text-muted">{user.username}</p>
                    </div>
                  </div>
                ),
              },
              {
                key: 'role',
                label: 'Роль',
                render: (user) => (
                  <span className="whitespace-nowrap text-sm">
                    {user.role_name}
                  </span>
                ),
              },
              {
                key: 'status',
                label: 'Статус',
                render: (user) => (
                  <div className="space-y-1">
                    <StatusBadge active={user.is_active} />
                    {user.must_change_password && (
                      <p className="whitespace-nowrap text-[11px] text-orange-600">
                        Требуется смена пароля
                      </p>
                    )}
                  </div>
                ),
              },
              {
                key: 'actions',
                label: 'Действия',
                className: 'text-right',
                render: (user) => (
                  <div className="flex justify-end gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label="Изменить роль"
                      title={
                        user.id === actor?.id
                          ? 'Собственную роль изменить нельзя'
                          : 'Изменить роль'
                      }
                      disabled={user.id === actor?.id || !roles.data}
                      onClick={() => setAction({ kind: 'role', user })}
                    >
                      <ShieldCheck />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label="Сбросить пароль"
                      title={
                        user.id === actor?.id
                          ? 'Свой пароль измените в настройках'
                          : 'Сбросить пароль'
                      }
                      disabled={user.id === actor?.id}
                      onClick={() => setAction({ kind: 'reset', user })}
                    >
                      <KeyRound />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      aria-label={
                        user.is_active ? 'Заблокировать' : 'Разблокировать'
                      }
                      title={
                        user.id === actor?.id
                          ? 'Собственную учётную запись заблокировать нельзя'
                          : user.is_active
                            ? 'Заблокировать'
                            : 'Разблокировать'
                      }
                      disabled={user.id === actor?.id}
                      onClick={() => setAction({ kind: 'block', user })}
                    >
                      {user.is_active ? <Ban /> : <UserCheck />}
                    </Button>
                  </div>
                ),
              },
            ]}
          />
        )}
        <div className="flex items-center justify-between border-t border-border px-5 py-3">
          <p className="text-xs text-muted">
            {users.data
              ? `${users.data.total === 0 ? 0 : page * 20 + 1}–${Math.min((page + 1) * 20, users.data.total)} из ${users.data.total}`
              : 'Загрузка…'}
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="icon"
              aria-label="Предыдущая страница"
              disabled={page === 0 || users.isPending}
              onClick={() => setPage(page - 1)}
            >
              <ChevronLeft />
            </Button>
            <Button
              variant="outline"
              size="icon"
              aria-label="Следующая страница"
              disabled={
                !users.data ||
                (page + 1) * 20 >= users.data.total ||
                users.isPending
              }
              onClick={() => setPage(page + 1)}
            >
              <ChevronRight />
            </Button>
          </div>
        </div>
      </section>
      <div className="mt-4 flex items-start gap-2 text-xs leading-5 text-muted">
        <ShieldCheck className="mt-0.5 size-4 shrink-0" />
        Изменение роли, блокировка и сброс пароля завершают активные сеансы
        сотрудника.
      </div>
      {action && (
        <UserDialog
          action={action}
          roles={roles.data?.items ?? []}
          onClose={() => setAction(null)}
          onSuccess={(text) => {
            setAction(null);
            setMessage(text);
            void client.invalidateQueries({ queryKey: ['users'] });
          }}
        />
      )}
    </>
  );
}
function UserDialog({
  action,
  roles,
  onClose,
  onSuccess,
}: {
  action: Action;
  roles: Role[];
  onClose: () => void;
  onSuccess: (message: string) => void;
}) {
  const [name, setName] = useState('');
  const [username, setUsername] = useState('');
  const [role, setRole] = useState(
    action.kind === 'role'
      ? action.user.role
      : (roles.find((role) => role.code === 'manager')?.code ??
          roles[0]?.code ??
          ''),
  );
  const [password, setPassword] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const titles = {
    create: 'Добавить пользователя',
    role: 'Изменить роль',
    block:
      action.kind === 'block' && action.user.is_active
        ? 'Заблокировать пользователя'
        : 'Разблокировать пользователя',
    reset: 'Сбросить пароль',
  };
  const description =
    action.kind === 'create'
      ? 'Создайте учётную запись. При первом входе сотрудник заменит временный пароль.'
      : `${action.user.display_name} · ${action.user.username}`;
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError('');
    if (
      action.kind === 'create' &&
      !/^[a-z0-9][a-z0-9._-]{2,63}$/i.test(username.trim())
    ) {
      setError(
        'Логин: 3–64 латинских буквы, цифры, точка, дефис или подчёркивание; первый символ — буква или цифра.',
      );
      return;
    }
    if (action.kind === 'create' && !name.trim()) {
      setError('Укажите имя сотрудника.');
      return;
    }
    if (
      (action.kind === 'create' || action.kind === 'reset') &&
      !password.trim()
    ) {
      setError('Пароль не может состоять только из пробелов.');
      return;
    }
    setPending(true);
    try {
      if (action.kind === 'create') {
        await request<User>('/users', {
          method: 'POST',
          body: {
            username: username.trim().toLowerCase(),
            display_name: name.trim(),
            role,
            password,
          },
        });
        onSuccess('Пользователь создан. При входе потребуется сменить пароль.');
      } else if (action.kind === 'role') {
        await request<User>(`/users/${action.user.id}`, {
          method: 'PATCH',
          body: { role },
        });
        onSuccess('Роль изменена. Активные сессии пользователя отозваны.');
      } else if (action.kind === 'block') {
        await request<User>(`/users/${action.user.id}`, {
          method: 'PATCH',
          body: { is_active: !action.user.is_active },
        });
        onSuccess(
          action.user.is_active
            ? 'Пользователь заблокирован. Активные сессии отозваны.'
            : 'Пользователь разблокирован.',
        );
      } else {
        await request(`/users/${action.user.id}/reset-password`, {
          method: 'POST',
          body: { new_password: password },
        });
        onSuccess(
          'Пароль сброшен. Сотруднику потребуется сменить временный пароль.',
        );
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(false);
    }
  }
  const submitText =
    action.kind === 'create'
      ? 'Создать пользователя'
      : action.kind === 'role'
        ? 'Сохранить роль'
        : action.kind === 'reset'
          ? 'Подтвердить сброс'
          : action.user.is_active
            ? 'Подтвердить блокировку'
            : 'Подтвердить разблокировку';
  return (
    <ConfirmDialog
      open
      onClose={onClose}
      title={titles[action.kind]}
      description={description}
      pending={pending}
    >
      <form onSubmit={submit} className="space-y-4">
        {error && <Notice>{error}</Notice>}
        {action.kind === 'create' && (
          <>
            <Field label="Имя сотрудника">
              {(id) => (
                <Input
                  id={id}
                  autoComplete="off"
                  required
                  maxLength={160}
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  disabled={pending}
                />
              )}
            </Field>
            <Field
              label="Логин"
              hint="3–64 символа: латинские буквы, цифры, точка, дефис или подчёркивание."
            >
              {(id) => (
                <Input
                  id={id}
                  autoComplete="off"
                  autoCapitalize="none"
                  spellCheck={false}
                  required
                  minLength={3}
                  maxLength={64}
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  disabled={pending}
                />
              )}
            </Field>
          </>
        )}
        {(action.kind === 'create' || action.kind === 'role') && (
          <Field label="Роль">
            {(id) => (
              <Select
                id={id}
                required
                value={role}
                onChange={(e) => setRole(e.target.value)}
                disabled={pending}
              >
                {roles.map((role) => (
                  <option key={role.code} value={role.code}>
                    {role.name}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        )}
        {(action.kind === 'create' || action.kind === 'reset') && (
          <Field
            label="Временный пароль"
            hint="От 12 до 128 символов. Передайте сотруднику по защищённому каналу."
          >
            {(id) => (
              <Input
                id={id}
                type="password"
                autoComplete="new-password"
                required
                minLength={12}
                maxLength={128}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={pending}
              />
            )}
          </Field>
        )}
        {action.kind === 'role' && (
          <p className="text-sm leading-6 text-muted">
            Новые права вступят в силу при следующем входе. Все текущие сеансы
            сотрудника будут завершены.
          </p>
        )}
        {action.kind === 'block' && (
          <p className="text-sm leading-6 text-muted">
            {action.user.is_active
              ? 'Сотрудник потеряет доступ к системе. Все текущие сеансы будут завершены. История действий сохранится.'
              : 'Сотрудник снова сможет войти в систему со своим паролем.'}
          </p>
        )}
        {action.kind === 'reset' && (
          <p className="text-sm leading-6 text-muted">
            Все текущие сеансы будут завершены. При следующем входе сотрудник
            должен будет установить новый пароль.
          </p>
        )}
        <div className="flex flex-wrap justify-end gap-3 border-t border-border pt-5">
          <Button
            variant="outline"
            type="button"
            disabled={pending}
            onClick={onClose}
          >
            Отмена
          </Button>
          <Button
            variant={
              action.kind === 'block' && action.user.is_active
                ? 'destructive'
                : 'default'
            }
            type="submit"
            disabled={
              pending || (action.kind === 'role' && role === action.user.role)
            }
          >
            {pending ? 'Сохраняем…' : submitText}
          </Button>
        </div>
      </form>
    </ConfirmDialog>
  );
}
