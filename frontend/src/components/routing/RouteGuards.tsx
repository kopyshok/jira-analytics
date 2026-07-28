import React from 'react';
import { Navigate, Outlet } from 'react-router';
import { AuthProvider } from '../AuthProvider';
import { GlobalTeamFilterProvider } from '../GlobalTeamFilterProvider';
import { GlobalPeriodFilterProvider } from '../shared/GlobalPeriodFilterProvider';
import { useAuth } from '../../hooks/useAuth';

export function AuthLayout() {
  return (
    <AuthProvider>
      <GlobalTeamFilterProvider>
        <GlobalPeriodFilterProvider>
          <Outlet />
        </GlobalPeriodFilterProvider>
      </GlobalTeamFilterProvider>
    </AuthProvider>
  );
}

export function ProtectedRoute({ children, adminOnly }: { children: React.ReactNode; adminOnly?: boolean }) {
  const { user, isLoading } = useAuth();
  if (isLoading) return null;
  if (!user) return <Navigate to="/login" replace />;
  if (adminOnly && user.role !== 'admin') return <Navigate to="/" replace />;
  return <>{children}</>;
}
