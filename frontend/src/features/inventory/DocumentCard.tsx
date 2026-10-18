import { Link } from 'react-router-dom';
import { StatusBadge } from '../../components/common';
import type { InventoryDocument } from './types';
import { documentNames } from './types';
export function DocumentCard({ document }: { document: InventoryDocument }) {
  return (
    <section className="space-y-4 rounded-xl border border-border bg-white p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-lg font-semibold"><Link className="text-primary hover:underline" to={`/inventory/documents/${document.id}`}>{document.number}</Link></h2>
        <StatusBadge active={!document.is_cancelled}>
          {document.is_cancelled
            ? 'Отменён'
            : documentNames[document.document_type]}
        </StatusBadge>
      </div>
      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-muted">Дата документа</dt>
          <dd>{document.document_date}</dd>
        </div>
        <div>
          <dt className="text-muted">Оператор</dt>
          <dd className="break-words">{document.created_by_name}</dd>
        </div>
        {document.recipient_name && (
          <div>
            <dt className="text-muted">Получатель</dt>
            <dd className="break-words">
              {document.recipient_name} · {document.recipient_personnel_number}{' '}
              · {document.recipient_department}
            </dd>
          </div>
        )}
        {document.receipt_purpose && (
          <div>
            <dt className="text-muted">Назначение</dt>
            <dd>
              {document.receipt_purpose === 'opening_balance'
                ? 'Начальный остаток'
                : 'Поставка'}
              {document.external_number && ` · ${document.external_number}`}
            </dd>
          </div>
        )}
      </dl>
      {document.comment && (
        <p className="whitespace-pre-wrap break-words text-sm">
          {document.comment}
        </p>
      )}
      {document.reason && (
        <p className="break-words text-sm">Причина отмены: {document.reason}</p>
      )}
      {document.reversal_of_id && (
        <Link
          className="block text-sm text-primary underline"
          to={`/inventory/documents/${document.reversal_of_id}`}
        >
          Исходный документ
        </Link>
      )}
      {document.reversal_id && (
        <Link
          className="block text-sm text-primary underline"
          to={`/inventory/documents/${document.reversal_id}`}
        >
          Документ отмены {document.reversal_number}
        </Link>
      )}
      <ul className="divide-y divide-border">
        {document.items.map((line) => (
          <li
            className="flex flex-wrap justify-between gap-3 py-3 text-sm"
            key={line.inventory_item_id}
          >
            <div className="min-w-0 flex-1 break-words">
              <Link
                className="text-primary hover:underline"
                to={`/inventory/items/${line.inventory_item_id}`}
              >
                {line.internal_code} · {line.model}
              </Link>
              <p className="text-xs text-muted">{line.manufacturer}</p>
            </div>
            <span>
              {line.quantity} шт. · движение {line.delta > 0 ? '+' : ''}
              {line.delta}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
