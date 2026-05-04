import { createContext, useContext } from 'react';
import type { UserProfile } from '../api/auth';

export interface AuthState {
  user: UserProfile | null;
  isLoading: boolean;
  login: (user: UserProfile) => void;
  logout: () => Promise<void>;
  updateUser: (u: UserProfile) => void;
}

export const AuthContext = createContext<AuthState | null>(null);

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
