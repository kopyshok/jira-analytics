import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router';
import { App, Button, Input, Segmented, Space, Tag, Tooltip, Typography } from 'antd';
import { CheckOutlined, DownloadOutlined, LeftOutlined, LockOutlined, RightOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import PageHeader from '../components/shared/PageHeader';
import KpiLedger from '../components/kpi/KpiLedger';
import KpiEmployeeCard from '../components/kpi/KpiEmployeeCard';
import KpiBreakdownModal, { type KpiBreakdownTarget } from '../components/kpi/KpiBreakdownModal';
import { useThemeTokens } from '../aurora/theme/useThemeTokens';
import { useGlobalTeamFilter } from '../hooks/useGlobalTeamFilter';
import {
  approveMonth, downloadKpiExport, fetchApproval, fetchKpiReport, fetchTeamsSummary,
  type KpiReportRow, type KpiTeamSummaryRow,
} from '../api/kpi';

const { Text } = Typography;

type PeriodMode = 'month' | 'quarter' | 'year';

const MONTH_NAMES_RU = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
];
const QUARTER_ROMAN = ['I', 'II', 'III', 'IV'];

function quarterOf(month: number): number {
  return Math.floor((month - 1) / 3) + 1;
}

function periodLabel(mode: PeriodMode, year: number, month: number): string {
  if (mode === 'year') return String(year);
  if (mode === 'quarter') return `${QUARTER_ROMAN[quarterOf(month) - 1]} квартал ${year}`;
  return `${MONTH_NAMES_RU[month - 1]} ${year}`;
}

function stepPeriod(mode: PeriodMode, year: number, month: number, dir: 1 | -1): { year: number; month: number } {
  const step = mode === 'year' ? 12 : mode === 'quarter' ? 3 : 1;
  const total = year * 12 + (month - 1) + dir * step;
  return { year: Math.floor(total / 12), month: (total % 12) + 1 };
}

export default function KpiPage() {
  const { notification } = App.useApp();
  const qc = useQueryClient();
  const t = useThemeTokens();
  const { selectedTeams, queryParams } = useGlobalTeamFilter();
  const [searchParams, setSearchParams] = useSearchParams();

  const mode = (searchParams.get('kpiMode') as PeriodMode | null) ?? 'month';
  const now = new Date();
  const year = Number(searchParams.get('kpiYear')) || now.getFullYear();
  const month = Number(searchParams.get('kpiMonth')) || now.getMonth() + 1;
  const direction = searchParams.get('kpiDirection') || undefined;

  const setPeriodParams = (next: { mode?: PeriodMode; year?: number; month?: number }) => {
    const p = new URLSearchParams(searchParams);
    p.set('kpiMode', next.mode ?? mode);
    p.set('kpiYear', String(next.year ?? year));
    p.set('kpiMonth', String(next.month ?? month));
    setSearchParams(p, { replace: true });
  };

  const [directionInput, setDirectionInput] = useState(direction ?? '');
  const applyDirection = () => {
    const p = new URLSearchParams(searchParams);
    if (directionInput.trim()) p.set('kpiDirection', directionInput.trim());
    else p.delete('kpiDirection');
    setSearchParams(p, { replace: true });
  };

  const [employeeCardRow, setEmployeeCardRow] = useState<KpiReportRow | null>(null);
  const [breakdownTarget, setBreakdownTarget] = useState<KpiBreakdownTarget | null>(null);

  const reportQuery = useQuery({
    queryKey: ['kpi', 'report', year, month, queryParams.teams, direction],
    queryFn: ({ signal }) => fetchKpiReport(
      { year, month, teams: queryParams.teams, direction }, signal,
    ),
    staleTime: 30_000,
    retry: 1,
  });

  const teamsSummaryQuery = useQuery({
    queryKey: ['kpi', 'teams-summary', year, month, direction],
    queryFn: ({ signal }) => fetchTeamsSummary(year, month, direction, signal),
    staleTime: 30_000,
    retry: 1,
  });

  const teamsSummaryByTeam = useMemo(() => {
    const m = new Map<string, KpiTeamSummaryRow>();
    for (const row of teamsSummaryQuery.data?.rows ?? []) m.set(row.team, row);
    return m;
  }, [teamsSummaryQuery.data]);

  // Утверждение — снимок на одну конкретную команду (см. модель KpiApproval).
  // Кнопка в шапке активна, только когда фильтр сужен до одной команды.
  const singleTeam = selectedTeams.length === 1 ? selectedTeams[0] : null;
  const approvalQuery = useQuery({
    queryKey: ['kpi', 'approval', singleTeam, year, month],
    queryFn: ({ signal }) => fetchApproval(singleTeam as string, year, month, signal),
    enabled: !!singleTeam,
  });

  const approveMut = useMutation({
    mutationFn: () => approveMonth({ team: singleTeam as string, year, month }),
    onSuccess: () => {
      notification.success({ title: 'Месяц утверждён', description: 'Результат заморожен снимком.' });
      qc.invalidateQueries({ queryKey: ['kpi', 'approval', singleTeam, year, month] });
    },
    onError: (e: Error) => notification.error({ title: 'Не удалось утвердить', description: e.message }),
  });

  const [exporting, setExporting] = useState(false);
  const handleExport = async () => {
    setExporting(true);
    try {
      await downloadKpiExport(
        { year, month, teams: queryParams.teams, direction },
        `kpi_${year}_${String(month).padStart(2, '0')}.xlsx`,
      );
    } catch (e) {
      notification.error({ title: 'Не удалось выгрузить', description: (e as Error).message });
    } finally {
      setExporting(false);
    }
  };

  const summary = reportQuery.data?.summary;
  const peopleCount = reportQuery.data?.rows.length ?? 0;

  return (
    <div>
      <PageHeader
        eyebrow="Обзор"
        title="KPI аналитиков"
        subtitle="Коэффициент эффективности по командам и людям"
        actions={(
          <Space wrap>
            {singleTeam ? (
              <Tag
                icon={<LockOutlined />}
                color={approvalQuery.data?.approved ? 'success' : 'default'}
              >
                {approvalQuery.data?.approved
                  ? `Утвердил ${approvalQuery.data.approved_by} · ${approvalQuery.data.approved_at?.slice(0, 10)}`
                  : 'Черновик, не утверждён'}
              </Tag>
            ) : (
              <Tooltip title="Выберите одну команду в фильтре, чтобы утвердить месяц">
                <Tag>Утверждение — по одной команде</Tag>
              </Tooltip>
            )}
            <Button
              type="primary"
              icon={<CheckOutlined />}
              disabled={!singleTeam || !!approvalQuery.data?.approved}
              loading={approveMut.isPending}
              onClick={() => approveMut.mutate()}
            >
              Утвердить месяц
            </Button>
            <Button icon={<DownloadOutlined />} loading={exporting} onClick={handleExport}>
              Выгрузить в Excel
            </Button>
          </Space>
        )}
      />

      <Space wrap size="middle" style={{ marginBottom: 16 }}>
        <Space size={4}>
          <Button
            icon={<LeftOutlined />}
            size="small"
            onClick={() => setPeriodParams(stepPeriod(mode, year, month, -1))}
          />
          <span style={{ minWidth: 150, textAlign: 'center', fontWeight: 600 }}>
            {periodLabel(mode, year, month)}
          </span>
          <Button
            icon={<RightOutlined />}
            size="small"
            onClick={() => setPeriodParams(stepPeriod(mode, year, month, 1))}
          />
        </Space>
        <Segmented
          value={mode}
          onChange={(v) => setPeriodParams({ mode: v as PeriodMode })}
          options={[
            { label: 'Месяц', value: 'month' },
            { label: 'Квартал', value: 'quarter' },
            { label: 'Год', value: 'year' },
          ]}
        />
        <Input
          placeholder="Продуктовое направление"
          allowClear
          style={{ width: 220 }}
          value={directionInput}
          onChange={(e) => setDirectionInput(e.target.value)}
          onPressEnter={applyDirection}
          onBlur={applyDirection}
        />
      </Space>

      {mode !== 'month' && (
        <Text type="secondary" style={{ display: 'block', marginBottom: 8, fontSize: 12 }}>
          Отчёт считается помесячно — показаны данные за {MONTH_NAMES_RU[month - 1].toLowerCase()} {year}.
        </Text>
      )}

      <div
        style={{
          display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 18,
          padding: '12px 18px', marginBottom: 14, borderRadius: 14,
          background: t.darkAccent, border: `1px solid ${t.border}`, fontSize: 12.5,
        }}
      >
        <span>
          <Text type="secondary" style={{ fontSize: 10.5, textTransform: 'uppercase', fontWeight: 600 }}>
            Средний КЭ
          </Text>{' '}
          <b className="num" style={{ fontSize: 13.5 }}>
            {summary?.avg_total != null ? `${Math.round(summary.avg_total)}%` : '—'}
          </b>
        </span>
        <span>
          <Text type="secondary" style={{ fontSize: 10.5, textTransform: 'uppercase', fontWeight: 600 }}>
            Ниже цели
          </Text>{' '}
          <b className="num" style={{ fontSize: 13.5 }}>
            {summary ? `${summary.below_target_count} из ${peopleCount} человек` : '—'}
          </b>
        </span>
        <span>
          <Text type="secondary" style={{ fontSize: 10.5, textTransform: 'uppercase', fontWeight: 600 }}>
            Метрик без данных
          </Text>{' '}
          <b className="num" style={{ fontSize: 13.5 }}>{summary?.no_data_metrics_count ?? '—'}</b>
        </span>
      </div>

      <KpiLedger
        rows={reportQuery.data?.rows ?? []}
        teamsSummaryByTeam={teamsSummaryByTeam}
        loading={reportQuery.isLoading}
        onOpenEmployee={setEmployeeCardRow}
        onOpenBreakdown={(row, metricCode, metricName) => setBreakdownTarget({ row, metricCode, metricName })}
      />

      <KpiEmployeeCard
        row={employeeCardRow}
        year={year}
        month={month}
        direction={direction}
        onClose={() => setEmployeeCardRow(null)}
        onOpenBreakdown={(metricCode, metricName) => {
          if (employeeCardRow) setBreakdownTarget({ row: employeeCardRow, metricCode, metricName });
        }}
      />

      <KpiBreakdownModal
        target={breakdownTarget}
        year={year}
        month={month}
        direction={direction}
        onClose={() => setBreakdownTarget(null)}
      />
    </div>
  );
}
