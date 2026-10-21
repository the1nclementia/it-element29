import { useState } from 'react';
import { Button } from '../../components/ui/button';
import { Notice } from '../../components/common';
import { request } from '../../lib/api';

export function ExportButton({
  kind,
  parameters = {},
  label,
}: {
  kind: 'balances' | 'movements';
  parameters?: Record<string, string | undefined>;
  label?: string;
}) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState('');
  async function download() {
    setPending(true);
    setError('');
    try {
      const query = new URLSearchParams();
      for (const [key, value] of Object.entries(parameters))
        if (value) query.set(key, value);
      const blob = await request<Blob>(
        `/inventory/exports/${kind}.xlsx?${query}`,
        { responseType: 'blob' },
      );
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `${kind}.xlsx`;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setPending(false);
    }
  }
  return (
    <div className="space-y-2">
      <Button
        variant="outline"
        disabled={pending}
        onClick={() => void download()}
      >
        {pending ? 'Готовим Excel…' : (label ?? 'Скачать Excel')}
      </Button>
      {error && <Notice>{error}</Notice>}
    </div>
  );
}
