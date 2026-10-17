import { type ReactNode } from 'react';
import { Outlet } from 'react-router';
import { useAuth } from '../../hooks/useAuth';
import { AuroraSidebar } from './AuroraSidebar';
import { AuroraTopbar } from './AuroraTopbar';
import FeedbackButton from '../../components/feedback/FeedbackButton';
import WhatsNewGate from '../../components/release-notes/WhatsNewGate';
import { HelpProvider } from '../../contexts/HelpContext';
import { usePageView } from '../../lib/usage/usePageView';
import { useHeartbeat } from '../../lib/usage/useHeartbeat';
import { useEventStream } from '../../hooks/useEventStream';
import { useThemeSync } from '../../hooks/useTheme';

function UsageTracker(): ReactNode {
  usePageView();
  useHeartbeat();
  return null;
}

export default function AuroraShell() {
  const { user } = useAuth();
  useEventStream();
  useThemeSync();

  return (
    <HelpProvider>
      <div
        style={{
          display: 'flex',
          gap: 16,
          height: '100vh',
          padding: 16,
          boxSizing: 'border-box',
        }}
      >
        <AuroraSidebar />
        <div
          style={{
            flex: 1,
            minWidth: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: 14,
          }}
        >
          <AuroraTopbar />
          <div className="scroll-y" style={{ flex: 1, paddingRight: 4 }}>
            <Outlet />
          </div>
        </div>
      </div>
      <FeedbackButton />
      {user && <UsageTracker />}
      {user && <WhatsNewGate />}
    </HelpProvider>
  );
}
