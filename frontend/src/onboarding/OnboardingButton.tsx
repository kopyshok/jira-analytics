import { Button } from 'antd';
import { FlagOutlined } from '@ant-design/icons';
import { useOnboarding } from './OnboardingContext';
import { progress } from './steps';

/** withLabel — подпись «Первые шаги» рядом со счётчиком (обложка «Швейцарская»). */
export default function OnboardingButton({ withLabel = false }: { withLabel?: boolean }) {
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
      {withLabel ? `Первые шаги · ${done}/${total}` : `${done}/${total}`}
    </Button>
  );
}
