import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { PageHeader, Notice } from '../components/common';
import { Button } from '../components/ui/button';
import { useAuth } from '../auth';
import { Catalog } from '../features/inventory/Catalog';
import { ItemForm } from '../features/inventory/ItemForm';
import { useDraft } from '../features/issues/state';
export function Inventory() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [parameters, setParameters] = useSearchParams();
  const [create, setCreate] = useState(parameters.get('create') === '1');
  const [added, setAdded] = useState('');
  const basket = useDraft('issue');
  const manage = user?.permissions.includes('inventory.manage');
  const issue = user?.permissions.includes('inventory.issue');
  return (
    <>
      <PageHeader
        title="Склад"
        description="Каталог расходных материалов, остатки и история операций"
      >
        <div className="sticky top-3 z-20 flex flex-wrap justify-end gap-2">
          <Button variant="outline" asChild>
            <Link to="/inventory/documents">Документы</Link>
          </Button>
          <Button variant="outline" asChild>
            <Link to="/inventory/catalogs">Справочники склада</Link>
          </Button>
          {manage && (
            <>
              <Button variant="outline" asChild>
                <Link to="/inventory/receipt">Поступление</Link>
              </Button>
              <Button onClick={() => setCreate(true)}>Создать позицию</Button>
            </>
          )}
        </div>
      </PageHeader>
      {added && (
        <div className="mb-4">
          <Notice success>
            <span>
              Позиция добавлена в корзину{' '}
              <span className="text-emerald-700">({added})</span>.{' '}
            </span>
            <Link className="font-semibold underline" to="/issues">
              Перейти в корзину
            </Link>
          </Notice>
        </div>
      )}
      {basket.locked && (
        <div className="mb-4">
          <Notice>Сначала завершите повтор отправки в разделе «Выдача».</Notice>
        </div>
      )}
      <Catalog
        disabled={basket.locked}
        basketCount={issue ? basket.draft.lines.length : undefined}
        onAdd={
          issue
            ? (item) => {
                basket.add(item);
                setAdded(item.internal_code);
              }
            : undefined
        }
      />
      {create && manage && (
        <ItemForm
          onClose={() => {
            setCreate(false);
            parameters.delete('create');
            setParameters(parameters, { replace: true });
          }}
          onSaved={(item) => navigate(`/inventory/items/${item.id}`)}
        />
      )}
    </>
  );
}
