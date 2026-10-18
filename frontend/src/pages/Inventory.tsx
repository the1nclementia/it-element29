import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { PageHeader, Notice } from '../components/common';
import { Button } from '../components/ui/button';
import { useAuth } from '../auth';
import { Catalog } from '../features/inventory/Catalog';
import { ItemForm } from '../features/inventory/ItemForm';
import { useDraft } from '../features/issues/state';
export function Inventory() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [create, setCreate] = useState(false);
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
        <div className="flex flex-wrap gap-2">
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
          {issue && (
            <Button variant="outline" asChild>
              <Link to="/issues">Корзина ({basket.draft.lines.length})</Link>
            </Button>
          )}
        </div>
      </PageHeader>
      {added && (
        <div className="mb-4">
          <Notice success>{added} добавлен в корзину.</Notice>
        </div>
      )}
      {basket.locked && (
        <div className="mb-4">
          <Notice>Сначала завершите повтор отправки в разделе «Выдача».</Notice>
        </div>
      )}
      <Catalog
        disabled={basket.locked}
        onAdd={
          issue
            ? (item) => {
                basket.add(item);
                setAdded(item.internal_code);
              }
            : undefined
        }
      />
      {create && (
        <ItemForm
          onClose={() => setCreate(false)}
          onSaved={(item) => navigate(`/inventory/items/${item.id}`)}
        />
      )}
    </>
  );
}
