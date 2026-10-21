import { useEffect, useState } from 'react';
import { Button, DatePicker, Empty, Segmented, Spin, Switch, Tooltip } from 'antd';
import { ExportOutlined, SettingOutlined, WarningOutlined } from '@ant-design/icons';
import AnalyticsFilters from '../../../components/analytics/AnalyticsFilters';
import AnalyticsTable from '../../../components/analytics/AnalyticsTable';
import AnalyticsReportSettings from '../../../components/analytics/AnalyticsReportSettings';
import AnalyticsIssueDrawer from '../../../components/analytics/AnalyticsIssueDrawer';
import DetailSheet from '../../../components/common/DetailSheet';
import type { AnalyticsPageState } from '../../../hooks/useAnalyticsPage';
import { LEVEL_LABELS, treeLevels, useAnalyticsLayout } from '../../../hooks/useAnalyticsLayout';
import { PcField, PcRow, PcTitle, PModule, PultScreen } from '../ui';

const fmt1 = (v: number) => v.toLocaleString('ru-RU', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

/**
 * «Иерархический отчёт по часам» в обложке «Пульт» (D-analytics):
 * Модули: сводка · переток · команды и отборы · дерево; карточка задачи — в панели подробностей.
 * Данные и действия — общий хук страницы.
 */
/** «2026-10-01» → «01.10.2026». */
const ddmmyyyy = (d: string) => `${d.slice(8, 10)}.${d.slice(5, 7)}.${d.slice(0, 4)}`;

export default function PultAnalyticsLayout({ page }: { page: AnalyticsPageState }) {
  const {
    selectedTeam, setSelectedTeam, urlFilters,
    localRange, setLocalRange, worklogMode, setWorklogMode, hierarchy, setHierarchy,
    columnSettingsOpen, setColumnSettingsOpen,
    data, isLoading, periodStart, periodEnd,
    handleFilterChange, hasActiveFilters, resetFilters, exportXlsx,
  } = page;
  // Подпись дерева — по тем же уровням, что и само дерево («Настройка отчёта» меняет порядок).
  const { resolved } = useAnalyticsLayout();
  // Карточка задачи — в панели подробностей поверх страницы (в Aurora — выезжающая справа).
  const [issue, setIssue] = useState<{ id: string; key: string; employee?: { id: string; name: string } } | null>(null);
  // Рабочая область ужалась под панель — выбранная строка дерева остаётся на виду.
  useEffect(() => {
    if (!issue) return;
    const frame = requestAnimationFrame(() =>
      document.querySelector('.an-tree-screen tr.tree-row-selected')?.scrollIntoView({ block: 'nearest', inline: 'start' }));
    return () => cancelAnimationFrame(frame);
  }, [issue]);

  const panel = (
    <PcRow>
      <PcTitle eyebrow="Аналитика" title="Иерархический отчёт по часам" />
      <div className="pc-push pc-group an-controls">
        <PcField label="Уточнить с / по">
          <span data-tour="analytics-period" style={{ display: 'inline-flex' }}>
            <DatePicker.RangePicker
              value={localRange}
              onChange={setLocalRange}
              // Пустой выбор = весь период строки состояния: его границы и видны, как на макете.
              placeholder={[ddmmyyyy(periodStart), ddmmyyyy(periodEnd)]}
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
            <PModule title="Сводка за период" className="an-summary">
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
            <PModule title="Переток внутри команды" className="an-flow">
              {flows.length === 0 ? (
                <div className="pm-empty an-flow-empty">Обмена часами между группами команды за период нет</div>
              ) : (
                <div className="an-flow-list" title="Часы, которыми группы обменялись внутри команды. Помощь извне считается отдельно.">
                  {flows.map((r) => (
                    <div key={r.subgroup_id} className="an-flow-row">
                      <b>{r.subgroup_name}</b>
                      {r.out_hours > 0 && <span className="num">→ −{Math.round(r.out_hours)} ч к соседям</span>}
                      {r.in_hours > 0 && <span className="num">← +{Math.round(r.in_hours)} ч от них</span>}
                    </div>
                  ))}
                </div>
              )}
            </PModule>
          </div>

          <PModule title="Команды" className="an-teams">
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

          <PModule
            title={`Дерево: ${treeLevels(resolved.visibleLevels, selectedTeam).map((l) => LEVEL_LABELS[l].toLowerCase()).join(' → ')}`}
            className="an-tree"
            extra={worklogMode === 'drawer' && (
              <span className="pm-push an-tree-hint">щелчок по задаче — карточка с ворклогами в панели</span>
            )}
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
        </>
      )}
      <DetailSheet
        open={!!issue}
        onClose={() => setIssue(null)}
        title="Карточка задачи"
        subtitle={`ворклоги за ${ddmmyyyy(periodStart)} – ${ddmmyyyy(periodEnd)}`}
        ariaLabel="Карточка задачи"
        className="an-sheet"
      >
        {issue && (
          <AnalyticsIssueDrawer
            docked
            issueId={issue.id}
            issueKey={issue.key}
            employee={issue.employee}
            periodStart={periodStart}
            periodEnd={periodEnd}
            onClose={() => setIssue(null)}
          />
        )}
      </DetailSheet>
    </PultScreen>
  );
}
