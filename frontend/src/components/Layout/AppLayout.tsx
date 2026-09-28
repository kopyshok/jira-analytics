import { useAppTheme } from '../../contexts/ThemeContext';
import AuroraShell from '../../aurora/shell/AuroraShell';
import { OnboardingProvider } from '../../onboarding/OnboardingProvider';
import OnboardingDrawer from '../../onboarding/OnboardingDrawer';
import TourRunner from '../../onboarding/TourRunner';

export default function AppLayout() {
  const { mode } = useAppTheme();
  // key на режиме форсит полный ремоунт при переключении тёмная↔светлая,
  // чтобы инлайновые стили (цвета через Proxy DARK_THEME) перечитали токены.
  // Провайдер — выше AuroraShell: состояние экскурсии не должно теряться при ремоунте.
  return (
    <OnboardingProvider>
      <AuroraShell key={`aurora-${mode}`} />
      <OnboardingDrawer />
      <TourRunner />
    </OnboardingProvider>
  );
}
