import * as Dialog from '@radix-ui/react-dialog';
import {
  AlertCircle,
  CheckCircle2,
  Inbox,
  Loader2,
  ShieldAlert,
  X,
  type LucideIcon,
} from 'lucide-react';
import { useId, type ReactNode } from 'react';
import { Button } from './ui/button';
import { cn } from '../lib/utils';
import { ApiError } from '../lib/api';
export function PageHeader({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children?: ReactNode;
}) {
  return (
    <div className="mb-7 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        <h1 className="break-words text-2xl font-semibold tracking-tight sm:text-[28px]">
          {title}
        </h1>
        <p className="mt-1.5 break-words text-sm text-muted">{description}</p>
      </div>
      {children}
    </div>
  );
}
export function LoadingState() {
  return (
    <div
      role="status"
      className="flex min-h-64 items-center justify-center gap-3 text-sm text-muted"
    >
      <Loader2 className="size-5 animate-spin" />
      Загружаем данные…
    </div>
  );
}
export function ErrorState({
  error,
  onRetry,
}: {
  error: Error;
  onRetry?: () => void;
}) {
  const denied = error instanceof ApiError && error.status === 403;
  return (
    <div
      role="alert"
      className="rounded-xl border border-border bg-white p-10 text-center"
    >
      <ShieldAlert className="mx-auto mb-4 size-9 text-orange-500" />
      <h2 className="text-lg font-semibold">
        {denied ? 'Недостаточно прав' : 'Не удалось загрузить данные'}
      </h2>
      <p className="mx-auto mt-2 max-w-md text-sm text-muted">
        {error.message}
      </p>
      {onRetry && (
        <Button className="mt-5" variant="outline" onClick={onRetry}>
          Повторить
        </Button>
      )}
    </div>
  );
}
export function EmptyState({
  title,
  description,
  icon: Icon = Inbox,
  children,
}: {
  title: string;
  description: string;
  icon?: LucideIcon;
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center px-5 py-14 text-center">
      <span className="mb-5 rounded-2xl bg-slate-50 p-4 text-slate-400">
        <Icon className="size-8" strokeWidth={1.5} />
      </span>
      <h2 className="text-base font-semibold">{title}</h2>
      <p className="mt-2 max-w-md text-sm leading-6 text-muted">
        {description}
      </p>
      {children}
    </div>
  );
}
export function StatusBadge({
  active,
  children,
}: {
  active?: boolean;
  children?: ReactNode;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium',
        active === true
          ? 'bg-emerald-50 text-emerald-700'
          : active === false
            ? 'bg-slate-100 text-slate-600'
            : 'bg-blue-50 text-blue-700',
      )}
    >
      <span
        className={cn(
          'size-1.5 rounded-full',
          active === true
            ? 'bg-emerald-500'
            : active === false
              ? 'bg-slate-400'
              : 'bg-blue-500',
        )}
      />
      {children ?? (active ? 'Активен' : 'Заблокирован')}
    </span>
  );
}
export function Notice({
  children,
  success = false,
}: {
  children: ReactNode;
  success?: boolean;
}) {
  const Icon = success ? CheckCircle2 : AlertCircle;
  return (
    <div
      role={success ? 'status' : 'alert'}
      className={cn(
        'flex gap-2.5 rounded-lg border p-3 text-sm leading-5',
        success
          ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
          : 'border-orange-200 bg-orange-50 text-orange-800',
      )}
    >
      <Icon className="mt-0.5 size-4 shrink-0" />
      {children}
    </div>
  );
}
export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: (id: string) => ReactNode;
  hint?: string;
}) {
  const id = useId();
  return (
    <div className="space-y-2">
      <label htmlFor={id} className="block text-sm font-medium">
        {label}
      </label>
      {children(id)}
      {hint && <p className="text-xs leading-5 text-muted">{hint}</p>}
    </div>
  );
}
export function ConfirmDialog({
  open,
  onClose,
  title,
  description,
  children,
  pending = false,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description: string;
  children: ReactNode;
  pending?: boolean;
}) {
  return (
    <Dialog.Root
      open={open}
      onOpenChange={(value) => {
        if (!value && !pending) onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-slate-950/35 backdrop-blur-[2px]" />
        <Dialog.Content
          onEscapeKeyDown={(event) => {
            if (pending) event.preventDefault();
          }}
          onPointerDownOutside={(event) => {
            if (pending) event.preventDefault();
          }}
          className="fixed left-1/2 top-1/2 z-50 max-h-[90dvh] w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-2xl border border-border bg-white p-6 shadow-2xl"
        >
          <Dialog.Title className="pr-8 text-xl font-semibold">
            {title}
          </Dialog.Title>
          <Dialog.Description className="mt-2 text-sm leading-6 text-muted">
            {description}
          </Dialog.Description>
          <Dialog.Close asChild>
            <Button
              disabled={pending}
              variant="ghost"
              size="icon"
              className="absolute right-4 top-4"
              aria-label="Закрыть"
            >
              <X />
            </Button>
          </Dialog.Close>
          <div className="mt-5">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
export interface Column<T> {
  key: string;
  label: string;
  render: (row: T) => ReactNode;
  className?: string;
}
export function DataTable<T extends { id: string }>({
  rows,
  columns,
}: {
  rows: T[];
  columns: Column<T>[];
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-border bg-slate-50/70">
            {columns.map((column) => (
              <th
                key={column.key}
                className={cn(
                  'px-5 py-3.5 text-xs font-medium text-muted',
                  column.className,
                )}
                scope="col"
              >
                {column.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr
              key={row.id}
              className="border-b border-border last:border-b-0 hover:bg-slate-50/60"
            >
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={cn('px-5 py-4', column.className)}
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
