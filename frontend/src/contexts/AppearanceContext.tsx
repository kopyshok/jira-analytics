import { createContext, useContext, useMemo, type ReactNode } from 'react';
import type { AppearanceSettings } from '../api/appearance';
import { useAppearance } from '../api/appearance';
import { DEFAULT_APPEARANCE, skinAppearance } from './appearanceDefaults';
import { useSkin } from './ThemeContext';
import { solidFill } from '../utils/readableColor';

export { DEFAULT_APPEARANCE } from './appearanceDefaults';

export const AppearanceContext = createContext<AppearanceSettings>(DEFAULT_APPEARANCE);

export function useAppearanceSettings(): AppearanceSettings {
  return useContext(AppearanceContext);
}

export function AppearanceProvider({ children }: { children: ReactNode }) {
  const { data } = useAppearance();
  const skin = useSkin();
  // В обложке — её палитра фаз; у Aurora значение то же, что сохранено.
  const value = useMemo(
    () => skinAppearance(data ?? DEFAULT_APPEARANCE, skin, solidFill),
    [data, skin],
  );
  return (
    <AppearanceContext.Provider value={value}>
      {children}
    </AppearanceContext.Provider>
  );
}
