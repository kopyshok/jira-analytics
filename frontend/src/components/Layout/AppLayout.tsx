import { useAppTheme } from '../../contexts/ThemeContext';
import AuroraShell from '../../aurora/shell/AuroraShell';
import ClassicShell from './ClassicShell';

export default function AppLayout() {
  const { isAurora } = useAppTheme();
  return isAurora ? <AuroraShell /> : <ClassicShell />;
}
