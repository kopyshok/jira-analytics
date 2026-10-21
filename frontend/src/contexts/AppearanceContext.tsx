import { createContext, useContext, useMemo, type ReactNode } from 'react';
import type { AppearanceSettings } from '../api/appearance';
import { useAppearance } from '../api/appearance';
import { DEFAULT_APPEARANCE } from './appearanceDefaults';
import { useSkin } from './ThemeContext';
import type { AppSkin } from '../utils/constants';
import { PULT_PHASE_COLORS } from '../skins/pult/palette';

export { DEFAULT_APPEARANCE } from './appearanceDefaults';

export const AppearanceContext = createContext<AppearanceSettings>(DEFAULT_APPEARANCE);

export function useAppearanceSettings(): AppearanceSettings {
  return useContext(AppearanceContext);
}

/**
 * Цвета фаз под обложку: значения по умолчанию заменяются палитрой обложки,
 * свои цвета пользователя остаются. Без обложки — тот же объект.
 */
export function skinAppearance(a: AppearanceSettings, skin: AppSkin | null): AppearanceSettings {
  if (skin !== 'pult') return a;
  const defaults = DEFAULT_APPEARANCE.phase_colors as Record<string, string>;
  const current = a.phase_colors as Record<string, string>;
  const phase_colors = { ...a.phase_colors };
  for (const key of Object.keys(phase_colors) as (keyof typeof phase_colors)[]) {
    if ((current[key] ?? '').toLowerCase() === (defaults[key] ?? '').toLowerCase() && PULT_PHASE_COLORS[key]) {
      phase_colors[key] = PULT_PHASE_COLORS[key];
    }
  }
  return { ...a, phase_colors };
}

export function AppearanceProvider({ children }: { children: ReactNode }) {
  const { data } = useAppearance();
  const skin = useSkin();
  const value = useMemo(() => skinAppearance(data ?? DEFAULT_APPEARANCE, skin), [data, skin]);
  return (
    <AppearanceContext.Provider value={value}>
      {children}
    </AppearanceContext.Provider>
  );
}
