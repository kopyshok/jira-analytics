import { useState } from 'react';
import { Button, DatePicker, Empty, Segmented, Spin, Switch, Tooltip } from 'antd';
import { ExportOutlined, SettingOutlined, WarningOutlined } from '@ant-design/icons';
import AnalyticsFilters from '../../../components/analytics/AnalyticsFilters';
import AnalyticsTable from '../../../components/analytics/AnalyticsTable';
import AnalyticsReportSettings from '../../../components/analytics/AnalyticsReportSettings';
import AnalyticsIssueDrawer from '../../../components/analytics/AnalyticsIssueDrawer';
import type { AnalyticsPageState } from '../../../hooks/useAnalyticsPage';
import { PcField, PcRow, PcTitle, PModule, PultScreen } from '../ui';

const fmt1 = (v: number) => v.toLocaleString('ru-RU', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

/**
 * «Иерархический отчёт по часам» в обложке «Пульт» (D-analytics):
 * М1 сводка · М2 переток · М3 команды и отборы · М4 дерево · М5 задача.
 * Данные и действия — общий хук страницы.
 */
export default function PultAnalyticsLayout({ page }: { page: AnalyticsPageState }) {
  const {
    selectedTeam, setSelectedTeam, urlFilters,
    localRange, setLocalRange, worklogMode, setWorklogMode, hierarchy, setHierarchy,
    columnSettingsOpen, setColumnSettingsOpen,
    data, isLoading, periodStart, periodEnd,
    handleFilterChange, hasActiveFilters, resetFilters, exportXlsx,
  } = page;
  // Карточка задачи встроена справа от дерева (в Aurora — выезжающая панель).
  const [issue, setIssue] = useState<{ id: string; key: string } | null>(null);

  const panel = (
    <PcRow>
      <PcTitle eyebrow="Аналитика" title="Иерархический отчёт по часам" />
      <div className="pc-push pc-group an-controls">
        <PcField label="Уточнить с / по">
          <span data-tour="analytics-period" style={{ display: 'inline-flex' }}>
            <DatePicker.RangePicker
              value={localRange}
              onChange={setLocalRange}
              placeholder={['Уточнить с', 'по']}
              allowClear
              format="DD.MM.YYYY"
              style={{ width: 240 }}
            />
          </span>
        </PcField>
        <PcField label="Ворклоги">
          <Segmented
            className="pc-accent-seg"
            value={worklogMode}
            onChange={(v) => setWorklogMode(v as 'inline' | 'drawer')}
            options={[
              { label: 'inline', value: 'inline' },
              { label: 'drawer', value: 'drawer' },
            ]}
          />
        </PcField>
        <PcField label="Иерархия">
          <Tooltip title="Задачи деревом до самого верхнего родителя">
            <span className="an-switch" data-tour="analytics-hierarchy">
              <Switch checked={hierarchy} onChange={setHierarchy} />
              <b className="num">{hierarchy ? 'ВКЛ' : 'ВЫКЛ'}</b>
            </span>
          </Tooltip>
        </PcField>
        <span className="an-hint">задачи деревом до<br />верхнего родителя</span>
        <Button
          icon={<SettingOutlined />}
          onClick={() => setColumnSettingsOpen(true)}
          data-tour="analytics-settings"
        >
          Настройка отчёта
        </Button>
        <Button type="primary" icon={<ExportOutlined />} onClick={exportXlsx}>
          Экспорт XLSX
        </Button>
      </div>
    </PcRow>
  );

  const totals = data?.grand_totals;
  const pct = totals?.plan_hours && totals.plan_hours > 0 ? (totals.fact_hours / totals.plan_hours) * 100 : null;
  const flows = (data?.subgroup_flow ?? []).filter((i) => i.out_hours > 0 || i.in_hours > 0);

  return (
    <PultScreen panel={panel} bodyClassName="an-pult">
      <AnalyticsReportSettings
        open={columnSettingsOpen}
        onClose={() => setColumnSettingsOpen(false)}
      />

      {isLoading && <div className="pm-empty"><Spin /></div>}
      {!isLoading && !data?.teams.length && (
        <div className="pm an-empty">
          <Empty description="Нет данных за выбранный период">
            {hasActiveFilters && (
              <Button type="primary" onClick={resetFilters}>
                Сбросить фильтры
              </Button>
            )}
          </Empty>
        </div>
      )}

      {!isLoading && data && totals && data.teams.length > 0 && (
        <>
          <div className="an-top">
            <PModule n={1} title="Сводка за период" className="an-summary">
              <div className="an-screens" data-tour="analytics-kpi">
                <div className="an-screen">
                  <span className="pc-cap">Σ часов факт</span>
                  <b className="num an-big">{fmt1(totals.fact_hours)}</b>
                </div>
                <div className="an-screen">
                  <span className="pc-cap">Σ часов план</span>
                  <b className="num">{totals.plan_hours != null ? Math.round(totals.plan_hours).toLocaleString('ru-RU') : '—'}</b>
                </div>
                <div className="an-screen">
                  <span className="pc-cap">% выполнения</span>
                  <span className="an-pct">
                    <b className={`num${pct != null && pct > 110 ? ' is-bad' : ''}`}>{pct == null ? '—' : `${pct.toFixed(0)}%`}</b>
                    {pct != null && (
                      <span className="an-meter"><i style={{ width: `${Math.min(pct, 100)}%` }} /><u /></span>
                    )}
                  </span>
                </div>
                <div className="an-screen">
                  <span className="pc-cap">Сотрудников</span>
                  <b className="num">{totals.employee_count}</b>
                </div>
                <div className="an-screen">
                  <span className="pc-cap">
                    {totals.foreign_hours > 0 && <WarningOutlined style={{ marginRight: 4 }} />}Чужих часов
                  </span>
                  <b className={`num${totals.foreign_hours > 0 ? ' is-warn' : ''}`}>
                    {fmt1(totals.foreign_hours)}
                    {totals.foreign_hours > 0 && <small> ({totals.foreign_pct.toFixed(0)}%)</small>}
                  </b>
                </div>
              </div>
            </PModule>
            {flows.length > 0 && (
              <PModule n={2} title="Переток внутри команды" className="an-flow">
                <div className="an-flow-list" title="Часы, которыми группы обменялись внутри команды. Помощь извне считается отдельно.">
                  {flows.map((r) => (
                    <div key={r.subgroup_id} className="an-flow-row">
                      <b>{r.subgroup_name}</b>
                      {r.out_hours > 0 && <span className="num">→ −{Math.round(r.out_hours)} ч к соседям</span>}
                      {r.in_hours > 0 && <span className="num">← +{Math.round(r.in_hours)} ч от них</span>}
                    </div>
                  ))}
                </div>
              </PModule>
            )}
          </div>

          <PModule n={flows.length > 0 ? 3 : 2} title="Команды" className="an-teams">
            <div className="an-teams-line">
              <div className="an-team-keys" role="group" aria-label="Команды">
                <button
                  type="button"
                  className={`an-team-key${selectedTeam === 'all' ? ' is-on' : ''}`}
                  aria-pressed={selectedTeam === 'all'}
                  onClick={() => setSelectedTeam('all')}
                >
                  Все команды <span className="num">{fmt1(totals.fact_hours)} ч</span>
                </button>
                {data.teams.map((t) => {
                  const key = t.team || '_none_';
                  const on = selectedTeam === t.team;
                  return (
                    <button
                      key={key}
                      type="button"
                      className={`an-team-key${on ? ' is-on' : ''}`}
                      aria-pressed={on}
                      onClick={() => setSelectedTeam(key)}
                    >
                      {t.team || 'Без команды'} <span className="num">{fmt1(t.totals.fact_hours)} ч</span>
                    </button>
                  );
                })}
              </div>
              <div className="pc-push" data-tour="analytics-filters">
                <AnalyticsFilters variant="panel" urlParams={urlFilters} onChange={handleFilterChange} />
              </div>
            </div>
          </PModule>

          <div className="an-main">
            <PModule
              n={flows.length > 0 ? 4 : 3}
              title="Дерево: команда → группа → роль → сотрудник → вид работ → категория → задача"
              className="an-tree"
            >
              <div className="pm-screen an-tree-screen" data-tour="analytics-table">
                <AnalyticsTable
                  data={data}
                  selectedTeam={selectedTeam}
                  worklogMode={worklogMode}
                  periodStart={periodStart}
                  periodEnd={periodEnd}
                  onOpenIssue={setIssue}
                  selectedIssueId={issue?.id ?? null}
                />
              </div>
            </PModule>
            <PModule n={flows.length > 0 ? 5 : 4} title="Задача" as="aside" className="an-issue">
              {issue ? (
                <AnalyticsIssueDrawer
                  docked
                  issueId={issue.id}
                  issueKey={issue.key}
                  periodStart={periodStart}
                  periodEnd={periodEnd}
                  onClose={() => setIssue(null)}
                />
              ) : (
                <div className="pm-empty">
                  {worklogMode === 'drawer'
                    ? 'Щёлкните задачу в дереве — здесь откроются её контекст, категория и ворклоги за период'
                    : 'Ворклоги показаны прямо в дереве. Чтобы открывать карточку задачи здесь, переключите «Ворклоги» на drawer'}
                </div>
              )}
            </PModule>
          </div>
        </>
      )}
    </PultScreen>
  );
}
