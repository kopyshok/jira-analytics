import { useAppTheme } from '../../contexts/ThemeContext';
import AuroraShell from '../../aurora/shell/AuroraShell';

export default function AppLayout() {
  const { mode } = useAppTheme();
  // key на режиме форсит полный ремоунт при переключении тёмная↔светлая,
  // чтобы инлайновые стили (цвета через Proxy DARK_THEME) перечитали токены.
  return <AuroraShell key={`aurora-${mode}`} />;
}
