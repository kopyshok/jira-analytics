import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router';
import { Alert, App, Button, Select, Space, Tag, Tooltip, Typography } from 'antd';
import { CheckOutlined, DownloadOutlined, LeftOutlined, LockOutlined, RightOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import kpiHelp from '../../../docs/help/kpi.md?raw';
import PageHeader from '../components/shared/PageHeader';
import KpiLedger, { KpiStatusLegend } from '../components/kpi/KpiLedger';
import KpiEmployeeCard from '../components/kpi/KpiEmployeeCard';
import KpiBreakdownModal, { type KpiBreakdownTarget } from '../components/kpi/KpiBreakdownModal';
import { useThemeTokens } from '../aurora/theme/useThemeTokens';
import { useGlobalTeamFilter } from '../hooks/useGlobalTeamFilter';
import { useRegisterHelp } from '../contexts/HelpContext';
import { formatDateOnly } from '../utils/format';
import { MONTH_NAMES } from '../utils/constants';
import {
  approveMonth, downloadKpiExport, fetchApproval, fetchDirections, fetchKpiReport, fetchTeamsSummary,
  type KpiReportRow, type KpiTeamSummaryRow,
} from '../api/kpi';

const { Text } = Typography;

// Полные русские названия месяцев — общий справочник `utils/constants.ts`,
// раньше был отдельно объявлен локальный дубликат (см. ревью, мелочи).
function periodLabel(year: number, month: number): string {
  return `${MONTH_NAMES[month]} ${year}`;
}

function stepPeriod(year: number, month: number, dir: 1 | -1): { year: number; month: number } {
  const total = year * 12 + (month - 1) + dir;
  return { year: Math.floor(total / 12), month: (total % 12) + 1 };
}

export default function KpiPage() {
  const { notification } = App.useApp();
  const qc = useQueryClient();
  const t = useThemeTokens();
  const { selectedTeams, queryParams } = useGlobalTeamFilter();
  const [searchParams, setSearchParams] = useSearchParams();
  useRegisterHelp('KPI аналитиков', kpiHelp);

  const now = new Date();
  const year = Number(searchParams.get('kpiYear')) || now.getFullYear();
  const month = Number(searchParams.get('kpiMonth')) || now.getMonth() + 1;
  const direction = searchParams.get('kpiDirection') || undefined;

  const setPeriodParams = (next: { year: number; month: number }) => {
    const p = new URLSearchParams(searchParams);
    p.set('kpiYear', String(next.year));
    p.set('kpiMonth', String(next.month));
    setSearchParams(p, { replace: true });
  };

  // Раньше единственным источником направлений был справочник атрибутов
  // (доступен только админу), поэтому фильтр был текстовым полем — теперь
  // отдельный лёгкий запрос доступен всем ролям (см. ревью, ВАЖНО 7).
  const directionsQuery = useQuery({ queryKey: ['kpi', 'directions'], queryFn: () => fetchDirections() });
  const applyDirection = (value: string | undefined) => {
    const p = new URLSearchParams(searchParams);
    if (value) p.set('kpiDirection', value);
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
    queryKey: ['kpi', 'teams-summary', year, month, queryParams.teams, direction],
    queryFn: ({ signal }) => fetchTeamsSummary(year, month, queryParams.teams, direction, signal),
    staleTime: 30_000,
    retry: 1,
  });

  const teamsSummaryByTeam = useMemo(() => {
    const m = new Map<string, KpiTeamSummaryRow>();
    for (const row of teamsSummaryQuery.data?.rows ?? []) m.set(row.team ?? 'Без команды', row);
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
      // Утверждение сбрасывает не только сам запрос об утверждении, но и
      // отчёт со сводкой — иначе плашка «месяц утверждён» не появится, пока
      // пользователь не перезагрузит страницу (см. ревью, ВАЖНО 7).
      qc.invalidateQueries({ queryKey: ['kpi', 'approval'] });
      qc.invalidateQueries({ queryKey: ['kpi', 'report'] });
      qc.invalidateQueries({ queryKey: ['kpi', 'teams-summary'] });
      qc.invalidateQueries({ queryKey: ['kpi', 'trend'] });
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

  // Команды с утверждённым месяцем — числа в ведомости заморожены снимком,
  // а не пересчитаны вживую (BLOCKER 1); показываем это явно, а не только
  // тегом в шапке для режима «одна команда».
  const approvedTeams = Object.entries(reportQuery.data?.approvals ?? {})
    .filter(([, a]) => a.approved)
    .map(([team]) => team);

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
                  ? `Утвердил ${approvalQuery.data.approved_by} · ${formatDateOnly(approvalQuery.data.approved_at)}`
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
            onClick={() => setPeriodParams(stepPeriod(year, month, -1))}
          />
          <span style={{ minWidth: 150, textAlign: 'center', fontWeight: 600 }}>
            {periodLabel(year, month)}
          </span>
          <Button
            icon={<RightOutlined />}
            size="small"
            onClick={() => setPeriodParams(stepPeriod(year, month, 1))}
          />
        </Space>
        <Select
          placeholder="Продуктовое направление"
          allowClear
          style={{ width: 220 }}
          loading={directionsQuery.isLoading}
          value={direction}
          onChange={(v) => applyDirection(v)}
          options={(directionsQuery.data ?? []).map((d) => ({ value: d, label: d }))}
        />
      </Space>

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

      {teamsSummaryQuery.isError && (
        // Сводка по командам (итог строки команды, дельта) не загрузилась —
        // без явного предупреждения руководитель принял бы прочерки за
        // «данных нет», а не за обрыв связи (см. ревью, ВАЖНО 6).
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 12 }}
          title="Не удалось загрузить сводку по командам"
          description={(teamsSummaryQuery.error as Error).message}
          action={<Button size="small" onClick={() => teamsSummaryQuery.refetch()}>Повторить</Button>}
        />
      )}

      {approvedTeams.length > 0 && (
        <Alert
          type="success"
          showIcon
          icon={<LockOutlined />}
          style={{ marginBottom: 12 }}
          title={
            approvedTeams.length === 1
              ? `Месяц утверждён по команде «${approvedTeams[0]}» — числа заморожены снимком, правки весов и нормативов на них не влияют.`
              : `Месяц утверждён по командам: ${approvedTeams.join(', ')} — их числа заморожены снимком.`
          }
        />
      )}

      <div style={{ marginBottom: 8 }}>
        <KpiStatusLegend />
      </div>

      <KpiLedger
        rows={reportQuery.data?.rows ?? []}
        teamsSummaryByTeam={teamsSummaryByTeam}
        loading={reportQuery.isLoading}
        error={reportQuery.isError ? (reportQuery.error as Error) : null}
        onRetry={() => reportQuery.refetch()}
        onOpenEmployee={setEmployeeCardRow}
        onOpenBreakdown={(row, metricCode, metricName) => setBreakdownTarget({ row, metricCode, metricName })}
      />

      <KpiEmployeeCard
        row={employeeCardRow}
        year={year}
        month={month}
        direction={direction}
        teams={queryParams.teams}
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
        teams={queryParams.teams}
        onClose={() => setBreakdownTarget(null)}
      />
    </div>
  );
}
