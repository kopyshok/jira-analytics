import { createContext, useContext, type ReactNode } from 'react';
import type { AppearanceSettings } from '../api/appearance';
import { useAppearance } from '../api/appearance';
import { DEFAULT_APPEARANCE } from './appearanceDefaults';

export { DEFAULT_APPEARANCE } from './appearanceDefaults';

export const AppearanceContext = createContext<AppearanceSettings>(DEFAULT_APPEARANCE);

export function useAppearanceSettings(): AppearanceSettings {
  return useContext(AppearanceContext);
}

export function AppearanceProvider({ children }: { children: ReactNode }) {
  const { data } = useAppearance();
  return (
    <AppearanceContext.Provider value={data ?? DEFAULT_APPEARANCE}>
      {children}
    </AppearanceContext.Provider>
  );
}
