import { Button } from 'antd';
import { FlagOutlined } from '@ant-design/icons';
import { useOnboarding } from './OnboardingContext';
import { progress } from './steps';

/** `labeled` — подпись «Первые шаги» вместо значка со счётчиком (оболочки скинов); счётчик — в подсказке. */
export default function OnboardingButton({ labeled = false }: { labeled?: boolean }) {
  const { status, team, openPanel } = useOnboarding();
  if (!status || status.me.hidden) return null;
  const { done, total } = progress(status, team !== null);
  if (done >= total) return null;
  if (labeled) {
    return (
      <Button
        onClick={openPanel}
        title={`Первые шаги: пройдено ${done} из ${total}`}
        data-testid="onboarding-button"
        data-tour="header-onboarding"
      >
        Первые шаги
      </Button>
    );
  }
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
