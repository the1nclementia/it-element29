import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './auth';
import { AppRoutes } from './App';
import './styles.css';
const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: false, staleTime: 30_000 },
    mutations: { retry: false },
  },
});
createRoot(document.getElementById('root')!).render(
  <QueryClientProvider client={queryClient}>
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  </QueryClientProvider>,
);
