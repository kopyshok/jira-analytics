import { createContext, useContext } from 'react';

export type GlobalPeriod = {
  year: number;
  quarter: number;
  month?: number;
};

export type GlobalPeriodCtx = {
  period: GlobalPeriod;
  setPeriod: (p: GlobalPeriod) => Promise<void>;
  saving: boolean;
  queryParams: { year: number; quarter: number; month?: number };
};

export const GlobalPeriodContext = createContext<GlobalPeriodCtx | null>(null);

export function useGlobalPeriod(): GlobalPeriodCtx {
  const ctx = useContext(GlobalPeriodContext);
  if (!ctx) throw new Error('useGlobalPeriod must be used inside GlobalPeriodFilterProvider');
  return ctx;
}
