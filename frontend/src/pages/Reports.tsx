import { useState } from 'react';
import { Link } from 'react-router-dom';
import { PageHeader, Field, ErrorState } from '../components/common';
import { Input, Select } from '../components/ui/input';
import { Button } from '../components/ui/button';
import { ExportButton } from '../features/inventory/ExportButton';
import { useOptions } from '../features/inventory/api';
import {
  documentNames,
  type Employee,
  type InventoryItem,
} from '../features/inventory/types';

export function Reports() {
  const [filters, setFilters] = useState<Record<string, string>>({});
  const items = useOptions<InventoryItem>('/inventory/items');
  const employees = useOptions<Employee>('/directory/employees');
  return (
    <>
      <PageHeader
        title="Отчёты склада"
        description="Excel с фактическими остатками и движениями. До 10 000 строк в одной выгрузке."
      />
      <div className="grid gap-5 lg:grid-cols-2">
        <section className="space-y-4 rounded-xl border border-border bg-white p-5">
          <h2 className="text-lg font-semibold">Остатки</h2>
          <p className="text-sm text-muted">
            Текущие остатки активных позиций. Для выгрузки по категории,
            производителю или наличию используйте фильтры каталога.
          </p>
          <ExportButton kind="balances" label="Скачать остатки в Excel" />
          <Button variant="outline" asChild>
            <Link to="/inventory">Выбрать фильтры каталога</Link>
          </Button>
        </section>
        <section className="space-y-4 rounded-xl border border-border bg-white p-5">
          <h2 className="text-lg font-semibold">Движения</h2>
          <Field label="Позиция для отчёта">
            {(id) => (
              <Select
                id={id}
                value={filters.item_id ?? ''}
                onChange={(event) =>
                  setFilters({ ...filters, item_id: event.target.value })
                }
              >
                <option value="">Все позиции</option>
                {items.data?.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.internal_code} · {item.model}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          {[
            ['date_from', 'Дата с'],
            ['date_to', 'Дата по'],
          ].map(([key, label]) => (
            <Field key={key} label={label}>
              {(id) => (
                <Input
                  id={id}
                  type="date"
                  value={filters[key] ?? ''}
                  onChange={(event) =>
                    setFilters({ ...filters, [key]: event.target.value })
                  }
                />
              )}
            </Field>
          ))}
          <ExportButton
            kind="movements"
            parameters={filters}
            label="Скачать движения в Excel"
          />
        </section>
      </div>
      <section
        className="mt-5 space-y-4 rounded-xl border border-border bg-white p-5"
        aria-label="Дополнительные фильтры движений"
      >
        <h2 className="text-lg font-semibold">Фильтры выгрузки движений</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Тип движения">
            {(id) => (
              <Select
                id={id}
                value={filters.document_type ?? ''}
                onChange={(event) =>
                  setFilters({ ...filters, document_type: event.target.value })
                }
              >
                <option value="">Все типы</option>
                {Object.entries(documentNames).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </Select>
            )}
          </Field>
          <Field label="Получатель отчёта">
            {(id) => (
              <Select
                id={id}
                disabled={employees.isPending}
                value={filters.recipient_employee_id ?? ''}
                onChange={(event) =>
                  setFilters({
                    ...filters,
                    recipient_employee_id: event.target.value,
                  })
                }
              >
                <option value="">Все получатели</option>
                {employees.data?.map((employee) => (
                  <option key={employee.id} value={employee.id}>
                    {employee.full_name} · {employee.personnel_number}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        </div>
        {[items, employees]
          .filter((query) => query.error)
          .map((query, index) => (
            <ErrorState
              key={index}
              error={query.error!}
              onRetry={() => void query.refetch()}
            />
          ))}
      </section>
    </>
  );
}
