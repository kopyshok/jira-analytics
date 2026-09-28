import { Button } from 'antd';
import { FlagOutlined } from '@ant-design/icons';
import { useOnboarding } from './OnboardingContext';
import { progress } from './steps';

export default function OnboardingButton() {
  const { status, team, openPanel } = useOnboarding();
  if (!status || status.me.hidden) return null;
  const { done, total } = progress(status, team !== null);
  if (done >= total) return null;
  return (
    <Button
      type="text"
      size="small"
      icon={<FlagOutlined />}
      onClick={openPanel}
      title="Первые шаги"
      aria-label="Первые шаги"
      data-testid="onboarding-button"
      data-tour="header-onboarding"
      style={{ color: 'var(--text-2)' }}
    >
      {done}/{total}
    </Button>
  );
}
