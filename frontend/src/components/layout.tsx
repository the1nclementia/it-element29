import { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import {
  Archive,
  ArrowLeftRight,
  BarChart3,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  FileChartColumn,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  Monitor,
  PackageOpen,
  Settings,
  ShieldCheck,
  Users,
  Wrench,
  X,
  type LucideIcon,
} from 'lucide-react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { useAuth } from '../auth';
import { cn } from '../lib/utils';
import { Button } from './ui/button';
import { Notice } from './common';
export const modules: {
  path: string;
  label: string;
  permission: string;
  icon: LucideIcon;
  group: string;
  description: string;
}[] = [
  {
    path: '/',
    label: 'Обзор',
    permission: 'dashboard.read',
    icon: LayoutDashboard,
    group: 'Рабочее пространство',
    description: 'Состояние ИТ-ресурсов и последние события',
  },
  {
    path: '/inventory',
    label: 'Склад',
    permission: 'inventory.read',
    icon: Archive,
    group: 'Рабочее пространство',
    description: 'Расходные материалы, остатки и поступления',
  },
  {
    path: '/issues',
    label: 'Выдача',
    permission: 'inventory.issue',
    icon: PackageOpen,
    group: 'Рабочее пространство',
    description: 'Выдача расходных материалов сотрудникам',
  },
  {
    path: '/equipment',
    label: 'Оборудование',
    permission: 'equipment.read',
    icon: Monitor,
    group: 'Рабочее пространство',
    description: 'Единый реестр оборудования организации',
  },
  {
    path: '/movements',
    label: 'Перемещения',
    permission: 'movements.read',
    icon: ArrowLeftRight,
    group: 'Рабочее пространство',
    description: 'Перемещения оборудования между подразделениями',
  },
  {
    path: '/maintenance',
    label: 'Обслуживание',
    permission: 'maintenance.read',
    icon: Wrench,
    group: 'Рабочее пространство',
    description: 'Ремонт, обслуживание и состояние техники',
  },
  {
    path: '/history',
    label: 'История',
    permission: 'history.read',
    icon: History,
    group: 'Аналитика',
    description: 'История операций с ИТ-ресурсами',
  },
  {
    path: '/statistics',
    label: 'Статистика',
    permission: 'statistics.read',
    icon: BarChart3,
    group: 'Аналитика',
    description: 'Показатели использования оборудования и материалов',
  },
  {
    path: '/reports',
    label: 'Отчёты',
    permission: 'reports.read',
    icon: FileChartColumn,
    group: 'Аналитика',
    description: 'Отчётность по ресурсам организации',
  },
  {
    path: '/users',
    label: 'Пользователи',
    permission: 'users.manage',
    icon: Users,
    group: 'Управление',
    description: 'Учётные записи и права доступа',
  },
  {
    path: '/settings',
    label: 'Настройки',
    permission: 'settings.read',
    icon: Settings,
    group: 'Управление',
    description: 'Профиль, безопасность и сведения о системе',
  },
];
export function Brand({ compact = false }: { compact?: boolean }) {
  return compact ? (
    <span className="brand-mark">
      <img src="/brand/mark-original.png" alt="ИТ-элемент [29]" />
    </span>
  ) : (
    <span className="brand-window">
      <img src="/brand/wordmark-original.png" alt="ИТ-элемент [29]" />
    </span>
  );
}

export function Sidebar({
  collapsed = false,
  onNavigate,
}: {
  collapsed?: boolean;
  onNavigate?: () => void;
}) {
  const { user } = useAuth();

  const visible = modules.filter(
    (module) =>
      user?.permissions.includes(module.permission) &&
      (!user.must_change_password || module.path === '/settings'),
  );

  const groups = ['Рабочее пространство', 'Аналитика', 'Управление'];

  return (
    <div className="flex h-full flex-col">
      <div
        className={cn(
          'flex h-20 shrink-0 items-center border-b border-border',
          collapsed ? 'justify-center' : 'px-6',
        )}
      >
        <Link
          to={user?.must_change_password ? '/settings' : '/'}
          onClick={onNavigate}
          aria-label="ИТ-элемент [29] — главная"
        >
          <Brand compact={collapsed} />
        </Link>
      </div>

      <nav
        aria-label="Основная навигация"
        className="flex-1 space-y-6 overflow-y-auto px-3 py-6"
      >
        {groups.map((group) => {
          const items = visible.filter((module) => module.group === group);

          if (items.length === 0) return null;

          return (
            <div key={group}>
              {!collapsed && (
                <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-[.14em] text-slate-400">
                  {group}
                </p>
              )}

              <div className="space-y-1">
                {items.map(({ path, label, icon: Icon }) => (
                  <NavLink
                    key={path}
                    to={path}
                    end={path === '/'}
                    title={collapsed ? label : undefined}
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      cn(
                        'flex min-h-11 items-center gap-3 rounded-lg px-3 text-[13px] font-medium transition-colors',
                        collapsed && 'justify-center',
                        isActive
                          ? 'bg-blue-50 text-primary'
                          : 'text-muted hover:bg-slate-50 hover:text-foreground',
                      )
                    }
                  >
                    <Icon className="size-[19px] shrink-0" strokeWidth={1.8} />
                    <span className={collapsed ? 'sr-only' : ''}>{label}</span>
                  </NavLink>
                ))}
              </div>
            </div>
          );
        })}
      </nav>

      <div
        className={cn(
          'border-t border-border p-5 text-xs text-muted',
          collapsed && 'px-2 text-center',
        )}
      >
        {collapsed ? (
          <ShieldCheck className="mx-auto size-5 text-slate-400" />
        ) : (
          <>
            <div className="mb-2 flex items-center gap-2 font-medium text-slate-500">
              <ShieldCheck className="size-4" />
              Корпоративная система
            </div>
            <span className="text-[11px] text-slate-400">
              ИТ-элемент [29] · версия 0.1.0
            </span>
          </>
        )}
      </div>
    </div>
  );
}
export function Header({ onMenu }: { onMenu: () => void }) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');

  const name =
    modules.find((module) => module.path === location.pathname)?.label ??
    'Страница';

  const initials = (user?.display_name ?? '')
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join('');

  const handleLogout = async () => {
    setPending(true);
    setError('');

    try {
      await logout();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setPending(false);
    }
  };

  return (
    <>
      <header className="flex h-20 shrink-0 items-center justify-between gap-3 border-b border-border bg-white px-5 sm:px-8">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="icon"
            onClick={onMenu}
            aria-label="Открыть меню"
            className="lg:hidden"
          >
            <Menu />
          </Button>

          <div className="text-sm">
            <span className="hidden text-slate-400 sm:inline">
              Рабочее пространство
              <span className="mx-3 text-slate-300">/</span>
            </span>
            <span className="font-medium">{name}</span>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden text-right sm:block">
            <p className="max-w-52 truncate text-sm font-medium">
              {user?.display_name}
            </p>
            <p className="mt-0.5 text-xs text-muted">{user?.role_name}</p>
          </div>

          <Link
            to="/settings"
            aria-label="Мой профиль"
            className="flex size-10 items-center justify-center rounded-full bg-blue-50 text-sm font-semibold text-primary"
          >
            {initials}
          </Link>

          <span className="mx-1 hidden h-7 w-px bg-border sm:block" />

          <Button
            variant="ghost"
            size="icon"
            aria-label="Выйти"
            title="Выйти"
            disabled={pending}
            onClick={handleLogout}
          >
            <LogOut />
          </Button>
        </div>
      </header>

      {error && (
        <div className="px-5 pt-4">
          <Notice>{error}</Notice>
        </div>
      )}
    </>
  );
}
export function AppLayout() {
  const [collapsed, setCollapsed] = useState(false);
  const [mobile, setMobile] = useState(false);
  return (
    <div className="min-h-dvh">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[100] focus:rounded focus:bg-white focus:p-3"
      >
        Перейти к содержимому
      </a>
      <aside
        className={cn(
          'fixed inset-y-0 left-0 z-20 hidden border-r border-border bg-white transition-[width] lg:block',
          collapsed ? 'w-20' : 'w-64',
        )}
      >
        <Sidebar collapsed={collapsed} />
        <Button
          variant="outline"
          size="icon"
          className="absolute -right-3 top-[92px] size-6 rounded-full shadow-sm"
          aria-label={collapsed ? 'Развернуть меню' : 'Свернуть меню'}
          onClick={() => setCollapsed(!collapsed)}
        >
          {collapsed ? <ChevronRight /> : <ChevronLeft />}
        </Button>
      </aside>
      <Dialog.Root open={mobile} onOpenChange={setMobile}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-40 bg-slate-950/35 lg:hidden" />
          <Dialog.Content className="fixed inset-y-0 left-0 z-50 w-72 bg-white shadow-xl lg:hidden">
            <Dialog.Title className="sr-only">Меню навигации</Dialog.Title>
            <Dialog.Description className="sr-only">
              Разделы корпоративной системы
            </Dialog.Description>
            <Sidebar onNavigate={() => setMobile(false)} />
            <Dialog.Close asChild>
              <Button
                aria-label="Закрыть меню"
                variant="ghost"
                size="icon"
                className="absolute right-2 top-5"
              >
                <X />
              </Button>
            </Dialog.Close>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
      <div
        className={cn(
          'transition-[margin]',
          collapsed ? 'lg:ml-20' : 'lg:ml-64',
        )}
      >
        <Header onMenu={() => setMobile(true)} />
        <main
          id="main"
          className="mx-auto max-w-[1580px] px-5 py-7 sm:px-8 sm:py-8"
        >
          <div className="page-enter">
            <Outlet />
          </div>
        </main>
        <footer className="mx-auto flex max-w-[1580px] flex-wrap justify-between gap-2 px-5 pb-6 text-[11px] text-slate-400 sm:px-8">
          <span>ИТ-элемент [29] — управление ИТ-ресурсами</span>
          <span className="flex items-center gap-1.5">
            <ClipboardList className="size-3" />
            Единое рабочее пространство
          </span>
        </footer>
      </div>
    </div>
  );
}
