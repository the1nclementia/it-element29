import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { ApiError, refreshCsrf, request, setCsrf } from './lib/api';
import type { AuthResponse, User } from './types';
interface AuthState {
  user: User | null;
  loading: boolean;
  error: Error | null;
  restore: () => Promise<void>;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  changePassword: (
    current_password: string,
    new_password: string,
  ) => Promise<void>;
}
const AuthContext = createContext<AuthState | null>(null);
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const client = useQueryClient();
  const clear = useCallback(() => {
    setUser(null);
    setCsrf(null);
    client.clear();
  }, [client]);
  const restore = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      await refreshCsrf();
      setUser(await request<User>('/auth/me', { anonymous: true }));
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) clear();
      else setError(e as Error);
    } finally {
      setLoading(false);
    }
  }, [clear]);
  useEffect(() => {
    void restore();
    const requirePassword = () => {
      client.clear();
      setUser((previous) =>
        previous ? { ...previous, must_change_password: true } : null,
      );
    };
    window.addEventListener('auth:expired', clear);
    window.addEventListener('auth:password-required', requirePassword);
    return () => {
      window.removeEventListener('auth:expired', clear);
      window.removeEventListener('auth:password-required', requirePassword);
    };
  }, [clear, restore, client]);
  const accept = (result: AuthResponse) => {
    client.clear();
    setCsrf(result.csrf_token);
    setUser(result.user);
  };
  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        error,
        restore,
        login: async (username, password) => {
          accept(
            await request<AuthResponse>('/auth/login', {
              method: 'POST',
              body: { username, password },
              anonymous: true,
            }),
          );
        },
        logout: async () => {
          await request('/auth/logout', { method: 'POST' });
          clear();
        },
        changePassword: async (current_password, new_password) => {
          accept(
            await request<AuthResponse>('/auth/password', {
              method: 'POST',
              body: { current_password, new_password },
            }),
          );
        },
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('AuthProvider is required');
  return value;
}
