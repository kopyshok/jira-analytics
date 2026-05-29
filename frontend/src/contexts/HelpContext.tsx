import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

export interface HelpEntry {
  title: string;
  content: string;
}

interface HelpContextValue {
  current: HelpEntry | null;
  set: (entry: HelpEntry) => void;
  clear: () => void;
}

const HelpContext = createContext<HelpContextValue | null>(null);

export function HelpProvider({ children }: { children: ReactNode }) {
  const [current, setCurrent] = useState<HelpEntry | null>(null);
  const set = useCallback((entry: HelpEntry) => setCurrent(entry), []);
  const clear = useCallback(() => setCurrent(null), []);
  const value = useMemo(() => ({ current, set, clear }), [current, set, clear]);
  return <HelpContext.Provider value={value}>{children}</HelpContext.Provider>;
}

export function useHelpContext(): HelpContextValue {
  const ctx = useContext(HelpContext);
  if (!ctx) throw new Error('HelpContext is not mounted');
  return ctx;
}

export function useRegisterHelp(title: string, content: string) {
  const { set, clear } = useHelpContext();
  useEffect(() => {
    set({ title, content });
    return () => clear();
  }, [title, content, set, clear]);
}
