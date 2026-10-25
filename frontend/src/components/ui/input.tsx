import type { ComponentProps } from 'react';
import { cn } from '../../lib/utils';
export function Input({ className, ...props }: ComponentProps<'input'>) {
  return (
    <input
      className={cn(
        'flex h-11 w-full rounded-xl border border-border bg-white px-3 text-sm text-foreground placeholder:text-muted focus:border-primary focus:outline-none focus:ring-3 focus:ring-primary/20 disabled:bg-slate-50 disabled:opacity-60',
        className,
      )}
      {...props}
    />
  );
}
export function Select({ className, ...props }: ComponentProps<'select'>) {
  return (
    <select
      className={cn(
        'h-11 w-full rounded-xl border border-border bg-white px-3 text-sm focus:border-primary focus:outline-none focus:ring-3 focus:ring-primary/20',
        className,
      )}
      {...props}
    />
  );
}
