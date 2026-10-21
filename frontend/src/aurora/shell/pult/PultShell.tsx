import { type ReactNode } from 'react';
import { Outlet } from 'react-router';
import { useAuth } from '../../../hooks/useAuth';
import WhatsNewGate from '../../../components/release-notes/WhatsNewGate';
import TokenRenewalAlert from '../../../components/Layout/TokenRenewalAlert';
import { HelpProvider } from '../../../contexts/HelpContext';
import { usePageView } from '../../../lib/usage/usePageView';
import { useHeartbeat } from '../../../lib/usage/useHeartbeat';
import { useEventStream } from '../../../hooks/useEventStream';
import { useThemeSync } from '../../../hooks/useTheme';
import { PultRail } from './PultRail';
import { PultStatusBar } from './PultStatusBar';

function UsageTracker(): ReactNode {
  usePageView();
  useHeartbeat();
  return null;
}

/**
 * Оболочка обложки «Пульт»: слева узкий переключатель режимов (разделы),
 * в центре прокручиваемая рабочая область, снизу тёмная строка состояния
 * со всеми глобальными органами управления (включая обратную связь).
 */
export default function PultShell() {
  const { user } = useAuth();
  useEventStream();
  useThemeSync();

  return (
    <HelpProvider>
      <div className="pult-app">
        {/* Плашки администратору (ключ Jira/Confluence не продлился) — над рабочей областью. */}
        <div className="pult-alerts">
          <TokenRenewalAlert />
        </div>
        <div className="pult-main">
          <PultRail />
          <main className="pult-content scroll-y">
            <Outlet />
          </main>
        </div>
        <PultStatusBar />
      </div>
      {user && <UsageTracker />}
      {user && <WhatsNewGate />}
    </HelpProvider>
  );
}
