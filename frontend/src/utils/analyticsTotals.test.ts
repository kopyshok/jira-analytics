import { describe, expect, it } from 'vitest';
import dayjs from 'dayjs';
import type { NodeTotals } from '../types/api';
import { analyticsExportUrl, periodBounds, planPercent } from './analyticsTotals';

describe('analyticsTotals', () => {
  it('periodBounds: квартал и месяц', () => {
    expect(periodBounds(2026, 4)).toEqual({ start: '2026-10-01', end: '2026-12-31' });
    expect(periodBounds(2026, 1, 2)).toEqual({ start: '2026-02-01', end: '2026-02-28' });
  });

  it('planPercent: без плана — null', () => {
    expect(planPercent({ fact_hours: 50, plan_hours: 100 } as NodeTotals)).toBe(50);
    expect(planPercent({ fact_hours: 50, plan_hours: null } as NodeTotals)).toBeNull();
    expect(planPercent({ fact_hours: 50, plan_hours: 0 } as NodeTotals)).toBeNull();
  });

  it('analyticsExportUrl: те же отборы, что на экране', () => {
    const url = analyticsExportUrl('http://api', {
      period: { year: 2026, quarter: 4, month: null },
      localRange: [dayjs('2026-10-01'), dayjs('2026-10-16')],
      selectedTeam: 'all',
      selectedTeams: ['A', 'B'],
      selectedSubgroups: [],
      employeeId: 'e1',
      visibleColumns: ['plan_hours'],
      hierarchy: true,
    });
    expect(url).toBe(
      'http://api/analytics/report/export.xlsx?year=2026&quarter=4&start_date=2026-10-01&end_date=2026-10-16'
      + '&teams=A%2CB&employee_id=e1&columns=plan_hours&hierarchy=true',
    );
  });
});
