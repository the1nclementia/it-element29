import { useState, type FormEvent } from 'react';
import { Navigate } from 'react-router-dom';
import {
  ArrowRight,
  Eye,
  EyeOff,
  Layers3,
  LockKeyhole,
  ShieldCheck,
} from 'lucide-react';
import { useAuth } from '../auth';
import { Brand } from '../components/layout';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Field, Notice } from '../components/common';
import { LoginHeroErrorBoundary } from '../components/LoginHeroErrorBoundary';
import { LoginHeroBackdrop } from '../components/LoginHeroBackdrop';

export function Login() {
  const { user, login } = useAuth();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  if (user)
    return (
      <Navigate to={user.must_change_password ? '/settings' : '/'} replace />
    );
  async function submit(event: FormEvent) {
    event.preventDefault();
    setError('');
    setPending(true);
    try {
      await login(username.trim(), password);
    } catch (e) {
      setError((e as Error).message);
      setPassword('');
    } finally {
      setPending(false);
    }
  }
  return (
    <div className="grid min-h-dvh lg:grid-cols-[1.55fr_1fr]">
      <section className="login-hero relative hidden overflow-hidden px-16 py-12 text-foreground lg:flex lg:flex-col">
        <LoginHeroErrorBoundary onFallback={() => undefined}>
          <LoginHeroBackdrop />
        </LoginHeroErrorBoundary>
        <div className="relative">
          <span className="inline-flex items-center gap-2 rounded-full border border-foreground/10 bg-white/70 px-3 py-1.5 text-xs text-foreground shadow-sm backdrop-blur">
            <span className="size-1.5 rounded-full bg-primary" />
            Корпоративная система учёта
          </span>
        </div>
        <div className="relative my-auto max-w-lg py-20">
          <div className="mb-8 flex size-14 items-center justify-center rounded-2xl border border-white/80 bg-white/85 shadow-sm">
            <Layers3 className="size-7 text-primary" strokeWidth={1.5} />
          </div>
          <h1 className="text-[44px] font-semibold leading-[1.2] tracking-tight">
            Ваши ИТ-ресурсы.
            <br />
            <span className="text-primary">Всё на своих местах.</span>
          </h1>
          <p className="mt-6 max-w-sm text-base leading-7 text-muted">
            Единое пространство для команды: оборудование, расходные материалы и
            управление доступом.
          </p>
          <div className="login-hero-accent mt-10 h-1 w-12 rounded-full" />
        </div>
        <p className="relative text-xs text-muted">
          ИТ-элемент [29] · Для внутреннего использования
        </p>
      </section>
      <section className="flex flex-col bg-white px-6 py-10 sm:px-12">
        <div className="mx-auto w-full max-w-sm">
          <Brand />
        </div>
        <div className="mx-auto my-auto w-full max-w-sm py-16">
          <div className="mb-6 flex size-11 items-center justify-center rounded-xl bg-primary-light text-primary">
            <LockKeyhole className="size-5" />
          </div>
          <h2 className="text-3xl font-semibold tracking-tight">
            Добро пожаловать
          </h2>
          <p className="mb-8 mt-3 text-sm leading-6 text-muted">
            Войдите в свою учётную запись,
            <br />
            чтобы продолжить работу.
          </p>
          <form onSubmit={submit} className="space-y-5">
            {error && <Notice>{error}</Notice>}
            <Field label="Логин">
              {(id) => (
                <Input
                  id={id}
                  name="username"
                  autoComplete="username"
                  autoCapitalize="none"
                  spellCheck={false}
                  required
                  maxLength={128}
                  placeholder="Введите логин"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  disabled={pending}
                />
              )}
            </Field>
            <Field label="Пароль">
              {(id) => (
                <div className="relative">
                  <Input
                    id={id}
                    className="pr-12"
                    name="password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    required
                    maxLength={128}
                    placeholder="Введите пароль"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    disabled={pending}
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    className="absolute right-1 top-1"
                    aria-label={
                      showPassword ? 'Скрыть пароль' : 'Показать пароль'
                    }
                    aria-pressed={showPassword}
                    disabled={pending}
                    onClick={() => setShowPassword(!showPassword)}
                  >
                    {showPassword ? <EyeOff /> : <Eye />}
                  </Button>
                </div>
              )}
            </Field>
            <Button
              className="mt-2 h-11 w-full"
              disabled={pending}
              type="submit"
            >
              {pending ? 'Выполняется вход…' : 'Войти в систему'}
              <ArrowRight className="ml-auto" />
            </Button>
          </form>
          <p className="mt-6 text-center text-xs leading-5 text-muted">
            Нет доступа или забыли пароль?
            <br />
            Обратитесь к администратору системы.
          </p>
        </div>
        <div className="flex items-center justify-center gap-2 text-xs text-slate-400">
          <ShieldCheck className="size-4" />
          Доступ только для сотрудников организации
        </div>
        <p className="mt-3 text-center text-xs text-slate-400">Версия 0.1.0</p>
      </section>
    </div>
  );
}
