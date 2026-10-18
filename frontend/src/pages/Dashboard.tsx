import { useQuery } from '@tanstack/react-query';
import {
  Activity,
  Archive,
  ArrowDownToLine,
  ArrowLeftRight,
  ArrowUpRight,
  Boxes,
  CircleHelp,
  Clock3,
  Monitor,
  Package,
  ShieldCheck,
  TriangleAlert,
  Wrench,
  type LucideIcon,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { request } from '../lib/api';
import { formatDate } from '../lib/utils';
import type { Dashboard as DashboardData, Metric } from '../types';
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  StatusBadge,
} from '../components/common';
import { modules } from '../components/layout';
import { useAuth } from '../auth';
const icons: Record<string, LucideIcon> = {
  equipment_total: Monitor,
  equipment_active: Activity,
  equipment_stock: Archive,
  equipment_maintenance: Wrench,
  cartridge_balance: Package,
  issues_today: ArrowDownToLine,
  movements_month: ArrowLeftRight,
  low_stock: TriangleAlert,
};
export function StatCard({ metric }: { metric: Metric }) {
  const Icon = icons[metric.key] ?? Boxes;
  return (
    <article className="rounded-xl border border-border bg-white p-5 shadow-[0_2px_4px_0_#172b4d03]">
      <div className="flex items-start justify-between gap-2">
        <p className="text-[13px] font-medium text-muted">{metric.label}</p>
        <span className="rounded-lg bg-blue-50 p-2 text-primary">
          <Icon className="size-[18px]" strokeWidth={1.7} />
        </span>
      </div>
      <p
        className="mt-4 text-3xl font-semibold tracking-tight"
        aria-label={metric.value === null ? 'Значение недоступно' : undefined}
      >
        {metric.value === null ? '—' : metric.value.toLocaleString('ru-RU')}
      </p>
      <p className="mt-3 flex items-center gap-1.5 text-[11px] text-slate-400">
        <CircleHelp className="size-3" />
        {metric.available
          ? 'По данным системы'
          : 'Данные появятся после запуска модуля'}
      </p>
    </article>
  );
}
export function Dashboard() {
  const { user } = useAuth();
  const query = useQuery({
    queryKey: ['dashboard'],
    queryFn: ({ signal }) => request<DashboardData>('/dashboard', { signal }),
  });
  if (query.isPending) return <LoadingState />;
  if (query.error)
    return (
      <ErrorState error={query.error} onRetry={() => void query.refetch()} />
    );
  return (
    <>
      <PageHeader
        title="Обзор системы"
        description="Ресурсы организации и последние события в одном месте"
      >
        <span className="rounded-lg border border-border bg-white px-3 py-2 text-xs text-muted">
          {formatDate(new Date().toISOString())}
        </span>
      </PageHeader>
      <div className="mb-7 flex flex-wrap items-center justify-between gap-4 rounded-xl border border-blue-100 bg-gradient-to-r from-blue-50 to-white px-5 py-4">
        <div className="flex items-center gap-3">
          <span className="flex size-10 items-center justify-center rounded-lg bg-white text-primary">
            <ShieldCheck className="size-5" />
          </span>
          <div>
            <p className="text-sm font-semibold">Рабочее пространство готово</p>
            <p className="mt-1 text-xs leading-5 text-muted">
              Учитывайте поступления и выдачи, проверяйте складские остатки и
              историю документов.
            </p>
          </div>
        </div>
        <StatusBadge>Этап 3 · Склад и выдача</StatusBadge>
      </div>
      <div className="grid grid-cols-1 gap-4 min-[480px]:grid-cols-2 xl:grid-cols-4">
        {query.data.metrics.map((metric) => (
          <StatCard key={metric.key} metric={metric} />
        ))}
      </div>
      <div className="mt-7 grid gap-5 xl:grid-cols-[1.5fr_1fr]">
        <section className="rounded-xl border border-border bg-white">
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <h2 className="text-sm font-semibold">Последние события</h2>
            <Clock3 className="size-4 text-slate-400" />
          </div>
          {query.data.recent_events.length === 0 ? (
            <EmptyState
              title="Пока нет событий"
              description="Здесь появятся ваши действия в системе."
              icon={Clock3}
            />
          ) : (
            <ul className="divide-y divide-border px-5">
              {query.data.recent_events.map((event) => (
                <li key={event.id} className="flex gap-3 py-4">
                  <span className="mt-1.5 size-2 shrink-0 rounded-full bg-blue-400" />
                  <div>
                    <p className="text-sm">{event.title}</p>
                    <p className="mt-1 text-xs text-muted">
                      {formatDate(event.occurred_at)} ·{' '}
                      {new Date(event.occurred_at).toLocaleTimeString('ru-RU', {
                        hour: '2-digit',
                        minute: '2-digit',
                      })}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="rounded-xl border border-border bg-white">
          <div className="border-b border-border px-5 py-4">
            <h2 className="text-sm font-semibold">Разделы системы</h2>
          </div>
          <div className="space-y-1 p-3">
            {modules
              .filter(
                (module) =>
                  ['/inventory', '/equipment', '/users', '/settings'].includes(
                    module.path,
                  ) && user?.permissions.includes(module.permission),
              )
              .map(({ path, label, description, icon: Icon }) => (
                <Link
                  key={path}
                  to={path}
                  className="group flex items-center gap-3 rounded-lg p-3 transition hover:bg-slate-50"
                >
                  <span className="rounded-lg bg-slate-50 p-2.5 text-muted group-hover:bg-blue-50 group-hover:text-primary">
                    <Icon className="size-5" strokeWidth={1.7} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-medium">{label}</p>
                    <p className="mt-0.5 text-xs leading-5 text-muted">
                      {description}
                    </p>
                  </div>
                  <ArrowUpRight className="size-4 shrink-0 text-slate-400" />
                </Link>
              ))}
          </div>
        </section>
      </div>
    </>
  );
}
