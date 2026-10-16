import { useAppTheme } from '../../contexts/ThemeContext';
import AuroraShell from '../../aurora/shell/AuroraShell';
import { OnboardingProvider } from '../../onboarding/OnboardingProvider';
import OnboardingDrawer from '../../onboarding/OnboardingDrawer';
import TourRunner from '../../onboarding/TourRunner';

export default function AppLayout() {
  const { theme } = useAppTheme();
  // key на теме форсит полный ремоунт при любом переключении (тёмная↔светлая↔скин),
  // чтобы инлайновые стили (цвета через Proxy DARK_THEME) перечитали токены.
  // Провайдер — выше AuroraShell: состояние экскурсии не должно теряться при ремоунте.
  return (
    <OnboardingProvider>
      <AuroraShell key={theme} />
      <OnboardingDrawer />
      <TourRunner />
    </OnboardingProvider>
  );
}
