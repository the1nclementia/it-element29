import { useQuery } from '@tanstack/react-query';
import {
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Boxes,
  ClipboardList,
  Package,
  PackagePlus,
  Plus,
  TriangleAlert,
  type LucideIcon,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { request } from '../lib/api';
import { formatDate } from '../lib/utils';
import type { Dashboard as DashboardData, Metric } from '../types';
import type {
  InventoryDocument,
  InventoryItem,
  Page,
} from '../features/inventory/types';
import { documentNames } from '../features/inventory/types';
import {
  EmptyState,
  ErrorState,
  LoadingState,
  StatusBadge,
} from '../components/common';
import { useAuth } from '../auth';

const icons: Record<string, LucideIcon> = {
  cartridge_balance: Package,
  issues_today: ArrowDownToLine,
  low_stock: TriangleAlert,
};
const actions = [
  {
    label: 'Добавить номенклатуру',
    description: 'Новая позиция каталога',
    path: '/inventory?create=1',
    permission: 'inventory.manage',
    icon: Plus,
  },
  {
    label: 'Новое поступление',
    description: 'Пополнить склад',
    path: '/inventory/receipt',
    permission: 'inventory.manage',
    icon: PackagePlus,
  },
  {
    label: 'Оформить выдачу',
    description: 'Передать сотруднику',
    path: '/issues',
    permission: 'inventory.issue',
    icon: ArrowUpRight,
  },
  {
    label: 'Открыть склад',
    description: 'Каталог и остатки',
    path: '/inventory',
    permission: 'inventory.read',
    icon: Boxes,
  },
];

export function StatCard({ metric }: { metric: Metric }) {
  const Icon = icons[metric.key] ?? Boxes;
  return (
    <article className="surface-card flex items-start justify-between gap-4 p-6">
      <div>
        <p className="text-sm text-muted">{metric.label}</p>
        <p
          className="mt-3 text-[34px] font-semibold leading-none tracking-tight"
          aria-label={metric.value === null ? 'Значение недоступно' : undefined}
        >
          {metric.value === null ? '—' : metric.value.toLocaleString('ru-RU')}
        </p>
        <p className="mt-3 text-xs text-muted">
          {metric.value === null
            ? 'Значение временно недоступно'
            : 'По данным системы'}
        </p>
      </div>
      <span className="rounded-2xl bg-primary-light p-3 text-primary">
        <Icon className="size-5" strokeWidth={1.7} />
      </span>
    </article>
  );
}

export function Dashboard() {
  const { user } = useAuth();
  const canRead = !!user?.permissions.includes('inventory.read');
  const query = useQuery({
    queryKey: ['dashboard'],
    queryFn: ({ signal }) => request<DashboardData>('/dashboard', { signal }),
  });
  const documents = useQuery({
    queryKey: ['warehouse', 'dashboard-documents'],
    queryFn: ({ signal }) =>
      request<Page<InventoryDocument>>(
        '/inventory/documents?limit=5&offset=0',
        { signal },
      ),
    enabled: canRead,
  });
  const lowStock = useQuery({
    queryKey: ['warehouse', 'dashboard-low-stock'],
    queryFn: ({ signal }) =>
      request<Page<InventoryItem>>(
        '/inventory/items?low_stock=true&limit=5&offset=0',
        { signal },
      ),
    enabled: canRead,
  });
  const visibleActions = actions.filter((action) =>
    user?.permissions.includes(action.permission),
  );
  return (
    <div className="space-y-7 sm:space-y-8">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="mb-3 text-[11px] font-semibold tracking-[.18em] text-muted">
            РАБОЧЕЕ ПРОСТРАНСТВО
          </p>
          <h1 className="text-3xl font-semibold tracking-tight sm:text-[36px] sm:leading-tight">
            Добро пожаловать!
          </h1>
          <p className="mt-3 text-sm leading-6 text-muted sm:text-base">
            Управление складом картриджей и техникой
          </p>
        </div>
        <p className="text-xs text-muted">
          {formatDate(new Date().toISOString())}
        </p>
      </div>
      {visibleActions.length > 0 && (
        <section aria-labelledby="quick-actions-title">
          <h2 id="quick-actions-title" className="mb-4 text-base font-semibold">
            Быстрые действия
          </h2>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {visibleActions.map(({ label, description, path, icon: Icon }) => (
              <Link
                key={path}
                to={path}
                className="surface-card group flex min-h-28 items-center gap-3 p-5 transition-colors hover:border-primary/40 hover:bg-primary-light/40"
              >
                <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary-light text-primary">
                  <Icon className="size-5" strokeWidth={1.8} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-semibold leading-5">{label}</p>
                  <p className="mt-1 text-xs leading-5 text-muted">
                    {description}
                  </p>
                </div>
                <ArrowRight className="size-4 shrink-0 text-muted transition-transform group-hover:translate-x-0.5" />
              </Link>
            ))}
          </div>
        </section>
      )}
      {query.isPending ? (
        <LoadingState />
      ) : query.error ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-3">
          {query.data.metrics
            .filter((metric) => metric.key in icons && metric.available)
            .slice(0, 3)
            .map((metric) => (
              <StatCard key={metric.key} metric={metric} />
            ))}
        </div>
      )}
      {canRead && (
        <div className="grid items-start gap-5 xl:grid-cols-[1.45fr_1fr]">
          <section
            className="surface-card overflow-hidden"
            aria-labelledby="recent-documents-title"
          >
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border p-5 sm:px-6">
              <h2
                id="recent-documents-title"
                className="text-base font-semibold"
              >
                Последние документы
              </h2>
              <Link
                to="/inventory/documents"
                className="flex items-center gap-1 text-xs font-medium text-primary hover:text-primary-hover"
              >
                Все документы <ArrowRight className="size-3.5" />
              </Link>
            </div>
            {documents.isPending ? (
              <LoadingState />
            ) : documents.error ? (
              <ErrorState
                error={documents.error}
                onRetry={() => void documents.refetch()}
              />
            ) : documents.data.items.length === 0 ? (
              <EmptyState
                title="Документов пока нет"
                description="Оформите поступление или выдачу — документ появится здесь."
                icon={ClipboardList}
              />
            ) : (
              <ul className="divide-y divide-border">
                {documents.data.items.map((document) => (
                  <li key={document.id}>
                    <Link
                      to={`/inventory/documents/${document.id}`}
                      className="flex flex-wrap items-center gap-3 p-5 transition-colors hover:bg-background sm:px-6"
                    >
                      <span className="rounded-xl bg-background p-2.5 text-muted">
                        <ClipboardList className="size-4" />
                      </span>
                      <div className="min-w-0 flex-1 basis-32">
                        <p className="break-words text-sm font-medium">
                          {document.number}
                        </p>
                        <p className="mt-1 text-xs text-muted">
                          {documentNames[document.document_type]} ·{' '}
                          {formatDate(document.document_date)}
                        </p>
                      </div>
                      <StatusBadge
                        active={document.is_cancelled ? false : undefined}
                      >
                        {document.is_cancelled
                          ? 'Отменён'
                          : document.document_type === 'reversal'
                            ? 'Отмена'
                            : 'Проведён'}
                      </StatusBadge>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section
            className="surface-card overflow-hidden"
            aria-labelledby="low-stock-title"
          >
            <div className="flex items-center justify-between gap-3 border-b border-border p-5 sm:px-6">
              <h2 id="low-stock-title" className="text-base font-semibold">
                Требуют пополнения
              </h2>
              <TriangleAlert className="size-4 text-primary" />
            </div>
            {lowStock.isPending ? (
              <LoadingState />
            ) : lowStock.error ? (
              <ErrorState
                error={lowStock.error}
                onRetry={() => void lowStock.refetch()}
              />
            ) : lowStock.data.items.length === 0 ? (
              <EmptyState
                title="Все остатки в норме"
                description="Позиций с остатком ниже установленного минимума нет."
                icon={Package}
              />
            ) : (
              <>
                <ul className="divide-y divide-border">
                  {lowStock.data.items.map((item) => (
                    <li key={item.id}>
                      <Link
                        to={`/inventory/items/${item.id}`}
                        className="flex items-center gap-4 p-5 transition-colors hover:bg-background sm:px-6"
                      >
                        <div className="min-w-0 flex-1">
                          <p className="break-words text-sm font-medium">
                            {item.manufacturer_name} {item.model}
                          </p>
                          <p className="mt-1 text-xs text-muted">
                            {item.internal_code} · Минимум {item.min_stock} шт.
                          </p>
                        </div>
                        <span className="shrink-0 rounded-lg bg-primary-light px-2.5 py-1.5 text-sm font-semibold text-primary">
                          {item.balance} шт.
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
                <div className="border-t border-border p-5 sm:px-6">
                  <Link
                    to="/inventory?low_stock=true"
                    className="text-xs font-medium text-primary hover:text-primary-hover"
                  >
                    Показать все ({lowStock.data.total}){' '}
                    <ArrowRight className="ml-1 inline size-3.5" />
                  </Link>
                </div>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
