import { useCallback } from 'react';
import { useNavigate } from 'react-router';
import { LogOut } from 'lucide-react';
import { useAuth } from '../../../hooks/useAuth';
import { trackAction } from '../../../lib/usage/track';
import GlobalTeamFilterButton from '../../../components/Layout/GlobalTeamFilterButton';
import GlobalPeriodPicker from '../../../components/shared/GlobalPeriodPicker';
import GlobalHelpButton from '../../../components/Layout/GlobalHelpButton';
import SyncIndicator from '../../../components/Layout/SyncIndicator';
import ThemeSelect from '../../../components/Layout/ThemeSelect';
import OnboardingButton from '../../../onboarding/OnboardingButton';
import FeedbackButton from '../../../components/feedback/FeedbackButton';

function initials(name: string): string {
  return name
    .split(' ')
    .map((w) => w[0] || '')
    .join('')
    .toUpperCase()
    .slice(0, 2);
}

/**
 * Строка состояния «Пульта» — единственное место глобальных органов управления:
 * синхронизация, команды, период, первые шаги, обратная связь, справка, тема,
 * пользователь и выход. Выпадающие панели открываются вверх (места снизу нет).
 */
export function PultStatusBar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = useCallback(async () => {
    await logout();
    trackAction('logout');
    navigate('/login', { replace: true });
  }, [logout, navigate]);

  return (
    <footer className="pult-status" aria-label="Строка состояния">
      <div className="pult-sb-group">
        <SyncIndicator />
        {user && (
          <>
            <span className="pult-sb-field">
              <span className="pult-sb-cap" aria-hidden="true">Команды</span>
              <span data-tour="header-team" style={{ display: 'inline-flex' }}><GlobalTeamFilterButton /></span>
            </span>
            <span className="pult-sb-field">
              <span className="pult-sb-cap" aria-hidden="true">Период</span>
              <span data-tour="header-period" style={{ display: 'inline-flex' }}><GlobalPeriodPicker /></span>
            </span>
            <OnboardingButton />
          </>
        )}
      </div>
      <div className="pult-sb-group pult-sb-right">
        <FeedbackButton variant="bar" />
        {user && (
          <>
            <span data-tour="header-help" style={{ display: 'inline-flex' }}><GlobalHelpButton /></span>
            <span className="pult-sb-field">
              <span className="pult-sb-cap" aria-hidden="true">Тема</span>
              <ThemeSelect width={130} />
            </span>
            <span className="pult-sb-user" title={user.display_name}>
              <span className="pult-sb-ini" aria-hidden="true">{initials(user.display_name)}</span>
              <span className="pult-sb-name">{user.display_name}</span>
            </span>
            <button type="button" className="pult-sb-icon" title="Выйти" aria-label="Выйти" onClick={handleLogout}>
              <LogOut size={15} strokeWidth={1.6} />
            </button>
          </>
        )}
      </div>
    </footer>
  );
}
