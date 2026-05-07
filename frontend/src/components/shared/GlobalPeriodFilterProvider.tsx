import { useState, useEffect, useCallback, type ReactNode } from 'react';
import { GlobalPeriodContext, type GlobalPeriod } from '../../hooks/useGlobalPeriod';
import { api } from '../../api/client';
import { useAuth } from '../../hooks/useAuth';

const CURRENT = (() => {
  const d = new Date();
  return {
    year: d.getFullYear(),
    quarter: Math.floor(d.getMonth() / 3) + 1,
    month: d.getMonth() + 1,
  };
})();

export function GlobalPeriodFilterProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [period, setPeriodState] = useState<GlobalPeriod>(CURRENT);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!user) return;
    api.get<GlobalPeriod>('/users/me/period').then((p) => {
      if (p && p.year && p.quarter) setPeriodState({ year: p.year, quarter: p.quarter, month: p.month });
    }).catch(() => { /* ignore */ });
  }, [user]);

  const setPeriod = useCallback(async (p: GlobalPeriod) => {
    setPeriodState(p);
    setSaving(true);
    try {
      await api.put('/users/me/period', p);
    } finally {
      setSaving(false);
    }
  }, []);

  return (
    <GlobalPeriodContext.Provider value={{
      period, setPeriod, saving,
      queryParams: { year: period.year, quarter: period.quarter, month: period.month },
    }}>
      {children}
    </GlobalPeriodContext.Provider>
  );
}
