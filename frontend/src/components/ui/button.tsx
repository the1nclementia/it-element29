import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import type { ComponentProps } from 'react';
import { cn } from '../../lib/utils';
const buttonVariants = cva(
  'inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-xl text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-primary/40 disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-4 shrink-0',
  {
    variants: {
      variant: {
        default: 'bg-primary text-white hover:bg-primary-hover shadow-xs',
        outline:
          'border border-border bg-white hover:bg-slate-50 text-foreground',
        ghost: 'hover:bg-slate-100 text-muted',
        destructive: 'bg-red-600 text-white hover:bg-red-700',
      },
      size: { default: 'h-10 px-4', sm: 'h-8 px-3 text-xs', icon: 'size-9' },
    },
    defaultVariants: { variant: 'default', size: 'default' },
  },
);
export function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: ComponentProps<'button'> &
  VariantProps<typeof buttonVariants> & { asChild?: boolean }) {
  const Comp = asChild ? Slot : 'button';
  return (
    <Comp
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}
