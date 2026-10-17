import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import type { AnalyticsReportResponse } from '../../types/api';
import { CONFIGURABLE_COLUMN_LABELS } from '../../hooks/useAnalyticsColumns';
import AnalyticsTable from './AnalyticsTable';

const state = vi.hoisted(() => ({ visible: [] as string[] }));

vi.mock('../../hooks/useAnalyticsColumns', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../hooks/useAnalyticsColumns')>()),
  useAnalyticsColumns: () => ({ visible: state.visible }),
}));
vi.mock('../../hooks/useAnalyticsLayout', async (importOriginal) => {
  const orig = await importOriginal<typeof import('../../hooks/useAnalyticsLayout')>();
  return { ...orig, useAnalyticsLayout: () => ({ resolved: orig.resolveLayout(undefined) }) };
});
vi.mock('../../hooks/useGlobalPeriod', () => ({
  useGlobalPeriod: () => ({ period: { year: 2026, quarter: 3 } }),
}));
vi.mock('../../hooks/useGlobalTeamFilter', () => ({
  useGlobalTeamFilter: () => ({ selectedTeams: [] }),
}));
vi.mock('react-router', () => ({ useNavigate: () => () => {} }));
vi.mock('./AnalyticsIssueDrawer', () => ({ default: () => null }));

const data: AnalyticsReportResponse = {
  teams: [],
  grand_totals: {
    fact_hours: 0, plan_hours: null, pct_plan: null, pct_total: 0, pct_in_group: null,
    worklog_count: 0, issue_count: 0, employee_count: 0, avg_worklog_minutes: 0,
    foreign_issue_count: 0, foreign_hours: 0, foreign_pct: 0,
  },
};

function renderHeader(visible: string[]): string {
  state.visible = visible;
  return renderToStaticMarkup(
    <AnalyticsTable
      data={data}
      selectedTeam="all"
      worklogMode="inline"
      periodStart="2026-07-01"
      periodEnd="2026-09-30"
    />,
  );
}

const headerCells = (html: string) => (html.match(/<th[\s>]/g) ?? []).length;

describe('столбцы отчёта аналитики из «Настройки отчёта»', () => {
  it('выключенные галочки — только обязательные столбцы', () => {
    const html = renderHeader([]);
    expect(html).toContain('Группа / Задача');
    expect(html).toContain('Часы факт');
    expect(html).not.toContain('Ср.мин');
  });

  it('галочка «Ср. минут» показывает свой столбец', () => {
    expect(renderHeader(['avg_worklog_minutes'])).toContain('Ср.мин');
  });

  it.each(Object.keys(CONFIGURABLE_COLUMN_LABELS))(
    'галочка «%s» добавляет ровно один столбец',
    (key) => {
      expect(headerCells(renderHeader([key]))).toBe(headerCells(renderHeader([])) + 1);
    },
  );
});
