import { useCallback } from 'react';
import { useNavigate } from 'react-router';
import { LogOut } from 'lucide-react';
import { useAuth } from '../../hooks/useAuth';
import { trackAction } from '../../lib/usage/track';
import GlobalTeamFilterButton from '../../components/Layout/GlobalTeamFilterButton';
import GlobalPeriodPicker from '../../components/shared/GlobalPeriodPicker';
import GlobalHelpButton from '../../components/Layout/GlobalHelpButton';
import SyncIndicator from '../../components/Layout/SyncIndicator';
import { Avatar } from '../primitives/Avatar';
import { ThemeToggle } from './ThemeToggle';

export function AuroraTopbar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = useCallback(async () => {
    await logout();
    trackAction('logout');
    navigate('/login', { replace: true });
  }, [logout, navigate]);

  return (
    <div className="topbar">
      <div className="eyebrow">Анализ Jira · Планирование квартала</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <SyncIndicator />
        {user && (
          <>
            <GlobalTeamFilterButton />
            <GlobalPeriodPicker />
            <GlobalHelpButton />
            <ThemeToggle />
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              <Avatar name={user.display_name} size={30} />
              <span style={{ fontSize: 13, color: 'var(--text-2)' }}>{user.display_name}</span>
            </span>
            <button className="icon-btn" title="Выйти" onClick={handleLogout}>
              <LogOut size={17} strokeWidth={1.8} />
            </button>
          </>
        )}
      </div>
    </div>
  );
}
