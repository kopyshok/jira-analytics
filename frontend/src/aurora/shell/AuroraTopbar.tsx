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
import ThemeSelect from '../../components/Layout/ThemeSelect';
import OnboardingButton from '../../onboarding/OnboardingButton';

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
            <span data-tour="header-team" style={{ display: 'inline-flex' }}><GlobalTeamFilterButton /></span>
            <span data-tour="header-period" style={{ display: 'inline-flex' }}><GlobalPeriodPicker /></span>
            <OnboardingButton />
            <span data-tour="header-help" style={{ display: 'inline-flex' }}><GlobalHelpButton /></span>
            <ThemeSelect width={170} />
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
