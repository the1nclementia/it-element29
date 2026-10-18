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
export function ProtectedRoute({
  children,
  permission,
}: {
  children: ReactNode;
  permission?: string;
}) {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) return <Navigate to="/login" replace />;
  if (user.must_change_password && location.pathname !== '/settings')
    return <Navigate to="/settings" replace />;
  if (permission && !user.permissions.includes(permission))
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
  const { loading, error, restore } = useAuth();
  if (loading) return <LoadingState />;
  if (error)
    return (
      <div className="mx-auto max-w-lg px-5 py-20">
        <ErrorState error={error} onRetry={() => void restore()} />
      </div>
    );
  return (
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
        {modules
          .filter(
            (module) => !['/', '/users', '/settings'].includes(module.path),
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
  );
}
