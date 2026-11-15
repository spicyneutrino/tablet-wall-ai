import * as TabsPrimitive from '@radix-ui/react-tabs';
import { useCallback } from 'react';
import type { ComponentProps } from 'react';
import { clsx } from 'clsx';

export function Tabs({ className, ...props }: ComponentProps<typeof TabsPrimitive.Root>) {
  return <TabsPrimitive.Root className={clsx('tab-group', className)} {...props} />;
}
export function TabsList({ className, ...props }: ComponentProps<typeof TabsPrimitive.List>) {
  return <TabsPrimitive.List className={clsx('tabs', className)} {...props} />;
}
export function TabsTrigger({ className, autoFocus, ref, ...props }: ComponentProps<typeof TabsPrimitive.Trigger>) {
  const controlRef = useCallback((node: HTMLButtonElement | null) => {
    if (node) node.autofocus = !!autoFocus;
    if (typeof ref === 'function') return ref(node);
    if (ref) ref.current = node;
  }, [autoFocus, ref]);
  return <TabsPrimitive.Trigger className={clsx('tab', className)} autoFocus={autoFocus} ref={controlRef} {...props} />;
}
export function TabsContent({ className, ...props }: ComponentProps<typeof TabsPrimitive.Content>) {
  return <TabsPrimitive.Content className={clsx('tab-panel', className)} {...props} />;
}
