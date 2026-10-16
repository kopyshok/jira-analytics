import { useAppTheme } from '../../contexts/ThemeContext';
import AuroraShell from '../../aurora/shell/AuroraShell';
import PultShell from '../../aurora/shell/pult/PultShell';
import { OnboardingProvider } from '../../onboarding/OnboardingProvider';
import OnboardingDrawer from '../../onboarding/OnboardingDrawer';
import TourRunner from '../../onboarding/TourRunner';

export default function AppLayout() {
  const { theme, skin } = useAppTheme();
  // key на полном id темы форсит полный ремоунт при любом переключении темы,
  // чтобы инлайновые стили (цвета через Proxy DARK_THEME) перечитали токены.
  // Провайдер — выше оболочки: состояние экскурсии не должно теряться при ремоунте.
  return (
    <OnboardingProvider>
      {skin === 'pult' ? <PultShell key={theme} /> : <AuroraShell key={theme} />}
      <OnboardingDrawer />
      <TourRunner />
    </OnboardingProvider>
  );
}
