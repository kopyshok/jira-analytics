import { useAppTheme, useSkin } from '../../contexts/ThemeContext';
import AuroraShell from '../../aurora/shell/AuroraShell';
import WarmShell from '../../skins/warm/shell/WarmShell';
import { OnboardingProvider } from '../../onboarding/OnboardingProvider';
import OnboardingDrawer from '../../onboarding/OnboardingDrawer';
import TourRunner from '../../onboarding/TourRunner';

export default function AppLayout() {
  const { theme } = useAppTheme();
  const skin = useSkin();
  // key на теме форсит полный ремоунт при любом переключении (тёмная↔светлая↔скин),
  // чтобы инлайновые стили (цвета через Proxy DARK_THEME) перечитали токены.
  // Оболочка — по скину (у «Тёплой» своя, у тем Aurora — AuroraShell).
  // Провайдер — выше оболочки: состояние экскурсии не должно теряться при ремоунте.
  return (
    <OnboardingProvider>
      {skin === 'warm' ? <WarmShell key={theme} /> : <AuroraShell key={theme} />}
      <OnboardingDrawer />
      <TourRunner />
    </OnboardingProvider>
  );
}
