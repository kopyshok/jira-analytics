import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router';
import { Alert, App, Button, Card, Select, Space, Tabs, Tag, Tooltip, Typography } from 'antd';
import { CheckOutlined, DownloadOutlined, LockOutlined } from '@ant-design/icons';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import kpiHelp from '../../../docs/help/kpi.md?raw';
import PageHeader from '../components/shared/PageHeader';
import KpiLedger, { KpiStatusLegend } from '../components/kpi/KpiLedger';
import KpiEmployeeTab from '../components/kpi/KpiEmployeeTab';
import KpiBreakdownDock, { type KpiBreakdownTarget } from '../components/kpi/KpiBreakdownDock';
import KpiSummaryBar from '../components/kpi/KpiSummaryBar';
import KpiTeamMetricStrip from '../components/kpi/KpiTeamMetricStrip';
import KpiPeriodPicker from '../components/kpi/KpiPeriodPicker';
import { periodLabel, stepPeriod, type KpiPeriod } from '../utils/kpiPeriod';
import { useThemeTokens } from '../aurora/theme/useThemeTokens';
import { useGlobalTeamFilter } from '../hooks/useGlobalTeamFilter';
import { useRegisterHelp } from '../contexts/HelpContext';
import { formatDateOnly } from '../utils/format';
import {
  approveQuarter, downloadKpiExport, fetchApproval, fetchDirections, fetchKpiReport, fetchTeamsSummary,
  type KpiReportRow, type KpiTeamSummaryRow,
} from '../api/kpi';

const { Text } = Typography;

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
  // Длина периода живёт в адресе рядом с месяцем — ссылку на квартальную
  // ведомость можно переслать так же, как на месячную.
  const months = Math.min(24, Math.max(1, Number(searchParams.get('kpiMonths')) || 1));
  const period: KpiPeriod = { year, month, months };
  const direction = searchParams.get('kpiDirection') || undefined;

  const setPeriodParams = (next: KpiPeriod) => {
    const p = new URLSearchParams(searchParams);
    p.set('kpiYear', String(next.year));
    p.set('kpiMonth', String(next.month));
    p.set('kpiMonths', String(next.months));
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

  // Сотрудники открываются вкладками рядом с ведомостью: двух человек можно
  // держать рядом при сравнении, чего боковое окно не позволяло.
  const [openEmployees, setOpenEmployees] = useState<KpiReportRow[]>([]);
  const [activeTab, setActiveTab] = useState('ledger');
  const [breakdownTarget, setBreakdownTarget] = useState<KpiBreakdownTarget | null>(null);

  const openEmployee = (row: KpiReportRow) => {
    setOpenEmployees((prev) => (
      prev.some((e) => e.employee_id === row.employee_id) ? prev : [...prev, row]
    ));
    setActiveTab(`emp:${row.employee_id}`);
  };
  const closeEmployee = (employeeId: string) => {
    setOpenEmployees((prev) => prev.filter((e) => e.employee_id !== employeeId));
    setActiveTab('ledger');
  };

  const reportQuery = useQuery({
    queryKey: ['kpi', 'report', year, month, months, queryParams.teams, queryParams.subgroups, direction],
    queryFn: ({ signal }) => fetchKpiReport(
      { year, month, months, teams: queryParams.teams, subgroups: queryParams.subgroups, direction }, signal,
    ),
    staleTime: 30_000,
    retry: 1,
  });

  // Прошлый период такой же длины — только ради дельты на человека в
  // ведомости (квартал сравнивается с кварталом). Сводка по командам считает
  // свою дельту на сервере, но на людей её там нет.
  const prevPeriod = stepPeriod(period, -1);
  const prevReportQuery = useQuery({
    queryKey: ['kpi', 'report', prevPeriod.year, prevPeriod.month, months, queryParams.teams, queryParams.subgroups, direction],
    queryFn: ({ signal }) => fetchKpiReport(
      {
        year: prevPeriod.year, month: prevPeriod.month, months,
        teams: queryParams.teams, subgroups: queryParams.subgroups, direction,
      },
      signal,
    ),
    staleTime: 30_000,
    retry: 1,
  });

  const prevTotals = useMemo(() => {
    const m = new Map<string, number>();
    for (const row of prevReportQuery.data?.rows ?? []) {
      if (row.total != null) m.set(row.employee_id, row.total);
    }
    return m;
  }, [prevReportQuery.data]);

  const teamsSummaryQuery = useQuery({
    queryKey: ['kpi', 'teams-summary', year, month, months, queryParams.teams, queryParams.subgroups, direction],
    queryFn: ({ signal }) => fetchTeamsSummary(
      year, month, queryParams.teams, direction, signal, months, queryParams.subgroups,
    ),
    staleTime: 30_000,
    retry: 1,
  });

  const teamsSummaryByTeam = useMemo(() => {
    const m = new Map<string, KpiTeamSummaryRow>();
    for (const row of teamsSummaryQuery.data?.rows ?? []) m.set(row.team ?? 'Без команды', row);
    return m;
  }, [teamsSummaryQuery.data]);

  // Утверждение — снимок на одну конкретную команду за целый квартал (см.
  // модель KpiApproval). Кнопка активна, только когда фильтр сужен до одной
  // команды И на экране именно квартал, а не месяц или произвольный отрезок.
  const singleTeam = selectedTeams.length === 1 ? selectedTeams[0] : null;
  const approvalEnabled = reportQuery.data?.approval_enabled ?? false;
  const periodQuarter = reportQuery.data?.quarter ?? null;
  const canApprove = approvalEnabled && !!singleTeam && !!periodQuarter;

  const approvalQuery = useQuery({
    queryKey: ['kpi', 'approval', singleTeam, periodQuarter?.year, periodQuarter?.quarter],
    queryFn: ({ signal }) => fetchApproval(
      singleTeam as string, periodQuarter!.year, periodQuarter!.quarter, signal,
    ),
    enabled: !!singleTeam && !!periodQuarter && approvalEnabled,
  });

  const approveMut = useMutation({
    mutationFn: () => approveQuarter({
      team: singleTeam as string, year: periodQuarter!.year, quarter: periodQuarter!.quarter,
    }),
    onSuccess: () => {
      notification.success({ title: 'Квартал утверждён', description: 'Результат заморожен снимком.' });
      // Утверждение сбрасывает не только сам запрос об утверждении, но и
      // отчёт со сводкой — иначе плашка «квартал утверждён» не появится, пока
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
        { year, month, months, teams: queryParams.teams, subgroups: queryParams.subgroups, direction },
        `kpi_${year}_${String(month).padStart(2, '0')}${months > 1 ? `_${months}мес` : ''}.xlsx`,
      );
    } catch (e) {
      notification.error({ title: 'Не удалось выгрузить', description: (e as Error).message });
    } finally {
      setExporting(false);
    }
  };

  const rows = reportQuery.data?.rows ?? [];
  const summary = reportQuery.data?.summary;

  // Команды с утверждённым месяцем — числа в ведомости заморожены снимком,
  // а не пересчитаны вживую (BLOCKER 1); показываем это явно, а не только
  // тегом в шапке для режима «одна команда».
  const approvedTeams = Object.entries(reportQuery.data?.approvals ?? {})
    .filter(([, a]) => a.approved)
    .map(([team]) => team);

  const teamsInLedger = new Set(rows.map((r) => r.team ?? '__none__')).size;

  // Ранг человека внутри его команды — тот же расчёт, что и в ведомости.
  const rankOf = (row: KpiReportRow) => {
    const peers = rows
      .filter((r) => (r.team ?? null) === (row.team ?? null) && r.total != null)
      .sort((a, b) => (b.total ?? 0) - (a.total ?? 0));
    const place = peers.findIndex((r) => r.employee_id === row.employee_id) + 1;
    return place > 0 ? { place, of: peers.length } : undefined;
  };

  const ledgerTab = (
    <>
      <KpiSummaryBar
        summary={summary}
        rows={rows}
        prevRows={prevReportQuery.data?.rows ?? []}
        skipped={reportQuery.data?.skipped ?? []}
        teamsSummary={teamsSummaryQuery.data?.rows ?? []}
      />

      {/* Полоса метрик повторяет строку команды в ведомости один в один, если
          команда одна — показываем её только когда команд несколько и в
          таблице нет общего итога по всем сразу. */}
      {teamsInLedger > 1 && (
        <KpiTeamMetricStrip rows={rows} prevRows={prevReportQuery.data?.rows ?? []} />
      )}

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
              ? `Квартал утверждён по команде «${approvedTeams[0]}» — числа заморожены снимком, правки весов и нормативов на них не влияют.`
              : `Квартал утверждён по командам: ${approvedTeams.join(', ')} — их числа заморожены снимком.`
          }
        />
      )}

      {/* Ведомость занимает всю ширину: на квартале к метрикам добавляются
          колонки месяцев, и боковой блок отнимал у таблицы место, ради
          которого её и открывают. */}
      <div style={{ marginBottom: 14 }}>
        <Card size="small" title="Ведомость" styles={{ body: { padding: 0 } }}>
          <div style={{ padding: '10px 12px 0' }}>
            <KpiStatusLegend />
          </div>
          <KpiLedger
            rows={rows}
            teamsSummaryByTeam={teamsSummaryByTeam}
            loading={reportQuery.isLoading}
            error={reportQuery.isError ? (reportQuery.error as Error) : null}
            onRetry={() => reportQuery.refetch()}
            onOpenEmployee={openEmployee}
            onOpenBreakdown={(row, metricCode, metricName) => setBreakdownTarget({ row, metricCode, metricName })}
            selectedCell={breakdownTarget
              ? { employeeId: breakdownTarget.row.employee_id, metricCode: breakdownTarget.metricCode }
              : null}
            prevTotals={prevTotals}
            prevPeriodLabel={periodLabel(prevPeriod)}
          />
        </Card>
      </div>

      <KpiBreakdownDock
        target={breakdownTarget}
        year={year}
        month={month}
        months={months}
        direction={direction}
        teams={queryParams.teams}
        onClose={() => setBreakdownTarget(null)}
      />
    </>
  );

  const tabItems = [
    { key: 'ledger', label: 'Ведомость', children: ledgerTab },
    ...openEmployees.map((row) => ({
      key: `emp:${row.employee_id}`,
      label: row.employee_name,
      closable: true,
      children: (
        <KpiEmployeeTab
          row={rows.find((r) => r.employee_id === row.employee_id) ?? row}
          year={year}
          month={month}
          months={months}
          direction={direction}
          teams={queryParams.teams}
          teamSummary={teamsSummaryByTeam.get(row.team ?? 'Без команды')}
          rank={rankOf(row)}
          onOpenBreakdown={(metricCode, metricName) => {
            setBreakdownTarget({ row, metricCode, metricName });
            setActiveTab('ledger');
          }}
        />
      ),
    })),
  ];

  return (
    <div>
      <PageHeader
        eyebrow="Обзор"
        title="KPI аналитиков"
        subtitle="Коэффициент эффективности по командам и людям"
        actions={(
          <Space wrap>
            {/* Утверждение выключено правилами раздела — ни плашки, ни кнопки:
                показывать неактивную кнопку значило бы обещать действие,
                которого сейчас нет. */}
            {approvalEnabled && (
              <>
                {canApprove ? (
                  <Tag
                    icon={<LockOutlined />}
                    color={approvalQuery.data?.approved ? 'success' : 'default'}
                  >
                    {approvalQuery.data?.approved
                      ? `Утвердил ${approvalQuery.data.approved_by} · ${formatDateOnly(approvalQuery.data.approved_at)}`
                      : 'Черновик, не утверждён'}
                  </Tag>
                ) : (
                  <Tooltip
                    title={periodQuarter
                      ? 'Выберите одну команду в фильтре, чтобы утвердить квартал'
                      : 'Утверждается целый квартал — переключите период на квартал'}
                  >
                    <Tag>{periodQuarter ? 'Утверждение — по одной команде' : 'Утверждается только квартал'}</Tag>
                  </Tooltip>
                )}
                <Button
                  type="primary"
                  icon={<CheckOutlined />}
                  disabled={!canApprove || !!approvalQuery.data?.approved}
                  loading={approveMut.isPending}
                  onClick={() => approveMut.mutate()}
                >
                  Утвердить квартал
                </Button>
              </>
            )}
            <Button icon={<DownloadOutlined />} loading={exporting} onClick={handleExport}>
              Выгрузить в Excel
            </Button>
          </Space>
        )}
      />

      <Space wrap size="middle" style={{ marginBottom: 16 }}>
        <KpiPeriodPicker period={period} onChange={setPeriodParams} />
        <Select
          placeholder="Продуктовое направление"
          allowClear
          style={{ width: 220 }}
          loading={directionsQuery.isLoading}
          value={direction}
          onChange={(v) => applyDirection(v)}
          options={(directionsQuery.data ?? []).map((d) => ({ value: d, label: d }))}
        />
        {reportQuery.isFetching && <Text type="secondary" style={{ fontSize: 12 }}>обновляется…</Text>}
      </Space>

      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        type={openEmployees.length ? 'editable-card' : 'line'}
        hideAdd
        onEdit={(key, action) => {
          if (action === 'remove') closeEmployee(String(key).replace('emp:', ''));
        }}
        items={tabItems}
        // Цвет фона вкладок повторяет карточки страницы — иначе вкладка
        // сотрудника выглядит как чужой блок поверх ведомости.
        style={{ background: 'transparent', color: t.textPrimary }}
      />
    </div>
  );
}
