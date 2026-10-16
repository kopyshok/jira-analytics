import { useAppTheme } from '../../contexts/ThemeContext';
import AuroraShell from '../../aurora/shell/AuroraShell';
import ZonesShell from '../../aurora/shell/zones/ZonesShell';
import { OnboardingProvider } from '../../onboarding/OnboardingProvider';
import OnboardingDrawer from '../../onboarding/OnboardingDrawer';
import TourRunner from '../../onboarding/TourRunner';

export default function AppLayout() {
  const { theme, skin } = useAppTheme();
  // key на полном id темы форсит полный ремоунт при любом переключении
  // (тёмная↔светлая↔скин), чтобы инлайновые стили (цвета через Proxy DARK_THEME)
  // перечитали токены. Оболочка — по скину: у «Цветовых зон» своя.
  // Провайдер — выше оболочки: состояние экскурсии не должно теряться при ремоунте.
  return (
    <OnboardingProvider>
      {skin === 'zones' ? <ZonesShell key={theme} /> : <AuroraShell key={theme} />}
      <OnboardingDrawer />
      <TourRunner />
    </OnboardingProvider>
  );
}
