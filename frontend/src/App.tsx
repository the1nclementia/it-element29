import type { ReactNode } from 'react';
import { Navigate, Route, Routes, useLocation, Link } from 'react-router-dom';
import { useAuth } from './auth';
import { AppLayout, modules } from './components/layout';
import {
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
  StatusBadge,
} from './components/common';
import { Button } from './components/ui/button';
import { ApiError } from './lib/api';
import { Login } from './pages/Login';
import { Dashboard } from './pages/Dashboard';
import { Settings } from './pages/Settings';
import { Users } from './pages/Users';
import { Inventory } from './pages/Inventory';
import { ItemDetails } from './pages/ItemDetails';
import { Documents, DocumentDetails } from './pages/Documents';
import { Directory } from './pages/Directory';
import { Reports } from './pages/Reports';
import { Equipment } from './pages/Equipment';
import { Drafts } from './pages/Drafts';
import { StockForm } from './features/issues/StockForm';
import { WarehouseProvider } from './features/issues/state';
export function ProtectedRoute({
  children,
  permission,
}: {
  children: ReactNode;
  permission?: string | string[];
}) {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) return <Navigate to="/login" replace />;
  if (user.must_change_password && location.pathname !== '/settings')
    return <Navigate to="/settings" replace />;
  if (
    permission &&
    !(Array.isArray(permission) ? permission : [permission]).some((value) =>
      user.permissions.includes(value),
    )
  )
    return (
      <ErrorState
        error={
          new ApiError(
            403,
            'forbidden',
            'Этот раздел недоступен вашей роли. Обратитесь к администратору, если нужен доступ.',
          )
        }
      />
    );
  return children;
}
function Placeholder({ path }: { path: string }) {
  const module = modules.find((item) => item.path === path)!;
  return (
    <>
      <PageHeader title={module.label} description={module.description}>
        <StatusBadge>В разработке</StatusBadge>
      </PageHeader>
      <section className="rounded-xl border border-border bg-white">
        <EmptyState
          icon={module.icon}
          title="Раздел готовится к запуску"
          description="Функции этого раздела появятся на следующем этапе развития системы. Пока здесь нет данных и операций."
        >
          <Button className="mt-6" variant="outline" asChild>
            <Link to="/">Вернуться к обзору</Link>
          </Button>
        </EmptyState>
      </section>
    </>
  );
}
export function AppRoutes() {
  const { loading, error, restore, user } = useAuth();
  if (loading) return <LoadingState />;
  if (error)
    return (
      <div className="mx-auto max-w-lg px-5 py-20">
        <ErrorState error={error} onRetry={() => void restore()} />
      </div>
    );
  return (
    <WarehouseProvider key={user?.id ?? 'anonymous'}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          element={
            <ProtectedRoute>
              <AppLayout />
            </ProtectedRoute>
          }
        >
          <Route
            index
            element={
              <ProtectedRoute permission="dashboard.read">
                <Dashboard />
              </ProtectedRoute>
            }
          />
          <Route
            path="settings"
            element={
              <ProtectedRoute permission="settings.read">
                <Settings />
              </ProtectedRoute>
            }
          />
          <Route
            path="users"
            element={
              <ProtectedRoute permission="users.manage">
                <Users />
              </ProtectedRoute>
            }
          />
          <Route
            path="inventory"
            element={
              <ProtectedRoute permission="inventory.read">
                <Inventory />
              </ProtectedRoute>
            }
          />
          <Route
            path="inventory/items/:id"
            element={
              <ProtectedRoute permission="inventory.read">
                <ItemDetails />
              </ProtectedRoute>
            }
          />
          <Route
            path="equipment"
            element={
              <ProtectedRoute permission="equipment.read">
                <Equipment />
              </ProtectedRoute>
            }
          />
          <Route
            path="inventory/catalogs"
            element={
              <ProtectedRoute permission="inventory.read">
                <Directory key="inventory" inventory />
              </ProtectedRoute>
            }
          />
          <Route
            path="inventory/documents"
            element={
              <ProtectedRoute permission="inventory.read">
                <Documents />
              </ProtectedRoute>
            }
          />
          <Route
            path="history"
            element={
              <ProtectedRoute permission="inventory.read">
                <Documents />
              </ProtectedRoute>
            }
          />
          <Route
            path="reports"
            element={
              <ProtectedRoute permission="inventory.read">
                <Reports />
              </ProtectedRoute>
            }
          />
          <Route
            path="inventory/drafts"
            element={
              <ProtectedRoute
                permission={['inventory.issue', 'inventory.manage']}
              >
                <Drafts />
              </ProtectedRoute>
            }
          />
          <Route
            path="inventory/documents/:id"
            element={
              <ProtectedRoute permission="inventory.read">
                <DocumentDetails />
              </ProtectedRoute>
            }
          />
          <Route
            path="inventory/receipt"
            element={
              <ProtectedRoute permission="inventory.manage">
                <StockForm kind="receipt" />
              </ProtectedRoute>
            }
          />
          <Route
            path="issues"
            element={
              <ProtectedRoute permission="inventory.issue">
                <StockForm kind="issue" />
              </ProtectedRoute>
            }
          />
          <Route
            path="directory"
            element={
              <ProtectedRoute permission="directory.manage">
                <Directory key="directory" />
              </ProtectedRoute>
            }
          />
          {modules
            .filter(
              (module) =>
                ![
                  '/',
                  '/users',
                  '/settings',
                  '/inventory',
                  '/issues',
                  '/directory',
                  '/inventory/drafts',
                  '/inventory/receipt',
                  '/history',
                  '/reports',
                  '/equipment',
                ].includes(module.path),
            )
            .map((module) => (
              <Route
                key={module.path}
                path={module.path.slice(1)}
                element={
                  <ProtectedRoute permission={module.permission}>
                    <Placeholder path={module.path} />
                  </ProtectedRoute>
                }
              />
            ))}
          <Route
            path="*"
            element={
              <EmptyState
                title="Страница не найдена"
                description="Проверьте адрес или выберите нужный раздел в меню."
              >
                <Button className="mt-5" asChild>
                  <Link to="/">На главную</Link>
                </Button>
              </EmptyState>
            }
          />
        </Route>
      </Routes>
    </WarehouseProvider>
  );
}
