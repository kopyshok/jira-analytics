import { useAppTheme } from '../../contexts/ThemeContext';
import AuroraShell from '../../aurora/shell/AuroraShell';
import SwissShell from '../../aurora/shell/SwissShell';
import { OnboardingProvider } from '../../onboarding/OnboardingProvider';
import OnboardingDrawer from '../../onboarding/OnboardingDrawer';
import TourRunner from '../../onboarding/TourRunner';

export default function AppLayout() {
  const { theme, skin } = useAppTheme();
  // key на полном id темы форсит ремоунт при любом переключении (тёмная↔светлая↔обложка),
  // чтобы инлайновые стили (цвета через Proxy DARK_THEME) перечитали токены.
  // Провайдер — выше оболочки: состояние экскурсии не должно теряться при ремоунте.
  const Shell = skin === 'swiss' ? SwissShell : AuroraShell;
  return (
    <OnboardingProvider>
      <Shell key={theme} />
      <OnboardingDrawer />
      <TourRunner />
    </OnboardingProvider>
  );
}
