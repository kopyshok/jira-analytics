import { useAppTheme } from '../../contexts/ThemeContext';
import AuroraShell from '../../aurora/shell/AuroraShell';
import ClassicShell from './ClassicShell';

export default function AppLayout() {
  const { isAurora, mode } = useAppTheme();
  // key on `${isAurora}-${mode}` forces full subtree remount on dark↔light toggle
  // so JSX-baked inline styles (color/bg via DARK_THEME Proxy) re-read fresh tokens.
  const shellKey = isAurora ? `aurora-${mode ?? 'dark'}` : 'classic';
  return isAurora ? <AuroraShell key={shellKey} /> : <ClassicShell key={shellKey} />;
}
