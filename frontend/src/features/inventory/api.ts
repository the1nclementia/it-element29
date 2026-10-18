import { useQuery } from '@tanstack/react-query';
import { request } from '../../lib/api';
import type { Page } from './types';
export function useList<T>(
  path: string,
  parameters: Record<string, string | number | boolean | undefined> = {},
) {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(parameters))
    if (value !== undefined && value !== '') query.set(key, String(value));
  const url = `${path}?${query}`;
  return useQuery({
    queryKey: ['warehouse', url],
    queryFn: ({ signal }) => request<Page<T>>(url, { signal }),
  });
}
// Selectors fetch every page; the server still limits each request to 100 records.
export function useOptions<T>(path: string) {
  return useQuery({
    queryKey: ['warehouse', 'options', path],
    queryFn: async ({ signal }) => {
      const items: T[] = [];
      let total = 0;
      do {
        const page = await request<Page<T>>(
          `${path}?limit=100&offset=${items.length}`,
          { signal },
        );
        total = page.total;
        items.push(...page.items);
        if (!page.items.length) break;
      } while (items.length < total);
      return items;
    },
  });
}
export function sameOriginPhoto(path: string | null) {
  if (!path) return undefined;
  const url = new URL(path, window.location.origin);
  return url.origin === window.location.origin &&
    url.pathname.startsWith('/api/v1/inventory/')
    ? url.href
    : undefined;
}
