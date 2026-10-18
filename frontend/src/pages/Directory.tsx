import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../auth';
import { PageHeader } from '../components/common';
import { Button } from '../components/ui/button';
import {
  definitions,
  DirectoryManager,
} from '../features/directory/DirectoryManager';
export function Directory({ inventory = false }: { inventory?: boolean }) {
  const { user } = useAuth();
  const keys = inventory
    ? ['manufacturers', 'categories', 'printers']
    : ['departments', 'employees'];
  const [tab, setTab] = useState(keys[0]);
  const manage = !!user?.permissions.includes(
    inventory ? 'inventory.manage' : 'directory.manage',
  );
  return (
    <>
      <PageHeader
        title={inventory ? 'Справочники склада' : 'Справочники'}
        description={
          inventory
            ? 'Производители, категории и модели совместимых принтеров'
            : 'Подразделения и сотрудники — получатели расходных материалов'
        }
      >
        {inventory && (
          <Button variant="outline" asChild>
            <Link to="/inventory">К каталогу</Link>
          </Button>
        )}
      </PageHeader>
      <div
        className="mb-5 flex flex-wrap gap-2"
        role="tablist"
        aria-label="Справочники"
      >
        {keys.map((key) => (
          <Button
            role="tab"
            aria-selected={tab === key}
            key={key}
            variant={tab === key ? 'default' : 'outline'}
            onClick={() => setTab(key)}
          >
            {definitions[key].title}
          </Button>
        ))}
      </div>
      <DirectoryManager
        key={tab}
        definition={definitions[tab]}
        manage={manage}
      />
    </>
  );
}
