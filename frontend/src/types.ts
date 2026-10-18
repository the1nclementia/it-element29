export interface User {
  id: string;
  username: string;
  display_name: string;
  role: string;
  role_name: string;
  permissions: string[];
  is_active: boolean;
  must_change_password: boolean;
  created_at: string;
}
export interface Role {
  code: string;
  name: string;
  permissions: string[];
}
export interface Metric {
  key: string;
  label: string;
  value: number | null;
  available: boolean;
}
export interface Dashboard {
  metrics: Metric[];
  recent_events: { id: string; title: string; occurred_at: string }[];
}
export interface AuthResponse {
  user: User;
  csrf_token: string;
}
