import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, KeyRound, ShieldCheck } from 'lucide-react';
import { useAuth } from '../auth';
import { Field, Notice, PageHeader, StatusBadge } from '../components/common';
import { Input } from '../components/ui/input';
import { Button } from '../components/ui/button';
export function Settings() {
  const { user, changePassword } = useAuth();
  const [current, setCurrent] = useState('');
  const [password, setPassword] = useState('');
  const [repeat, setRepeat] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError('');
    setSuccess(false);
    if (password !== repeat) {
      setError('Новые пароли не совпадают.');
      return;
    }
    if (!password.trim()) {
      setError('Пароль не может состоять только из пробелов.');
      return;
    }
    setPending(true);
    try {
      await changePassword(current, password);
      setCurrent('');
      setPassword('');
      setRepeat('');
      setSuccess(true);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(false);
    }
  }
  return (
    <>
      <PageHeader
        title="Настройки"
        description="Ваш профиль, безопасность и сведения о системе"
      />
      {user?.must_change_password && (
        <div className="mb-6">
          <Notice>
            Перед началом работы замените временный пароль. Остальные разделы
            станут доступны после смены.
          </Notice>
        </div>
      )}
      <div className="grid items-start gap-6 xl:grid-cols-[1.2fr_1fr]">
        <section className="rounded-xl border border-border bg-white p-6">
          <div className="mb-6 flex items-center gap-3">
            <span className="rounded-lg bg-primary-light p-2.5 text-primary">
              <KeyRound className="size-5" />
            </span>
            <div>
              <h2 className="text-base font-semibold">Безопасность</h2>
              <p className="mt-1 text-xs text-muted">
                Смена пароля учётной записи
              </p>
            </div>
          </div>
          <form onSubmit={submit} className="max-w-md space-y-5">
            {error && <Notice>{error}</Notice>}
            {success && (
              <>
                <Notice success>Пароль успешно изменён</Notice>
                <Button variant="outline" asChild>
                  <Link to="/">
                    Перейти к обзору
                    <ArrowRight />
                  </Link>
                </Button>
              </>
            )}
            <Field label="Текущий пароль">
              {(id) => (
                <Input
                  id={id}
                  type="password"
                  autoComplete="current-password"
                  required
                  maxLength={128}
                  value={current}
                  onChange={(e) => setCurrent(e.target.value)}
                  disabled={pending}
                />
              )}
            </Field>
            <Field
              label="Новый пароль"
              hint="От 12 до 128 символов. Можно использовать длинную парольную фразу."
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
            <Field label="Повторите новый пароль">
              {(id) => (
                <Input
                  id={id}
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={12}
                  maxLength={128}
                  value={repeat}
                  onChange={(e) => setRepeat(e.target.value)}
                  disabled={pending}
                />
              )}
            </Field>
            <div className="border-t border-border pt-5">
              <Button type="submit" disabled={pending}>
                {pending ? 'Сохраняем…' : 'Изменить пароль'}
              </Button>
              <p className="mt-3 text-xs leading-5 text-muted">
                После смены пароля сеансы на других устройствах будут завершены.
              </p>
            </div>
          </form>
        </section>
        <div className="space-y-6">
          <section className="rounded-xl border border-border bg-white p-6">
            <h2 className="mb-5 text-base font-semibold">Мой профиль</h2>
            <dl className="space-y-4 text-sm">
              {[
                ['Имя', user?.display_name],
                ['Логин', user?.username],
                ['Роль', user?.role_name],
              ].map(([key, value]) => (
                <div key={key} className="flex flex-wrap justify-between gap-3">
                  <dt className="text-muted">{key}</dt>
                  <dd className="break-all font-medium">{value}</dd>
                </div>
              ))}
              <div className="flex justify-between">
                <dt className="text-muted">Статус</dt>
                <dd>
                  <StatusBadge active={user?.is_active} />
                </dd>
              </div>
            </dl>
          </section>
          <section className="rounded-xl border border-border bg-white p-6">
            <div className="mb-5 flex items-center gap-2">
              <ShieldCheck className="size-5 text-primary" />
              <h2 className="text-base font-semibold">О системе</h2>
            </div>
            <p className="text-sm font-medium">ИТ-элемент [29]</p>
            <p className="mt-2 text-sm leading-6 text-muted">
              Корпоративная система управления ИТ-ресурсами.
            </p>
            <div className="mt-5 flex justify-between border-t border-border pt-4 text-xs">
              <span className="text-muted">Версия приложения</span>
              <span className="font-medium">0.1.0 · Этап 3</span>
            </div>
          </section>
        </div>
      </div>
    </>
  );
}
