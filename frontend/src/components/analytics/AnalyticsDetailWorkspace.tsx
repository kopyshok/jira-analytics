import { useMemo, useState } from 'react';
import { Button, Empty, Input, Segmented, Select, Skeleton, Tag } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import { useQueryClient } from '@tanstack/react-query';
import type {
  AnalyticsCategoryNode,
  AnalyticsEmployeeNode,
  AnalyticsIssueNode,
  AnalyticsReportResponse,
  AnalyticsRoleNode,
  AnalyticsTeamNode,
  AnalyticsWorkTypeNode,
  NodeTotals,
} from '../../types/api';
import { useEmployeesForFilter } from '../../hooks/useAnalytics';
import { useAnalyticsColumns } from '../../hooks/useAnalyticsColumns';
import { useCategories } from '../../hooks/useCategories';
import { useIssueContext } from '../../hooks/useIssueContext';
import { useMandatoryWorkTypes } from '../../hooks/useMandatoryWorkTypes';
import { statusTagColor } from '../../utils/status';
import AnalyticsWorklogsBlock from './AnalyticsWorklogsBlock';
import IssueCategorizer from './IssueCategorizer';
import IssueContextBlock from './IssueContextBlock';
import './AnalyticsDetailWorkspace.css';

type DetailDepth = 'employees' | 'tasks' | 'worklogs';
type DetailRowKind = 'team' | 'role' | 'employee' | 'workType' | 'category' | 'issue';

interface DetailRow {
  key: string;
  depth: number;
  kind: DetailRowKind;
  label: string;
  marker: string;
  markerColor?: string;
  totals: NodeTotals;
  issue?: AnalyticsIssueNode;
  status?: string;
  statusCategory?: string | null;
}

interface AnalyticsFilterValues {
  employeeId?: string;
  workType?: string;
  category?: string;
  taskQ?: string;
}

interface Props {
  data: AnalyticsReportResponse;
  selectedTeam: string | 'all';
  onSelectTeam: (team: string | 'all') => void;
  urlParams: AnalyticsFilterValues;
  onFilterChange: (next: AnalyticsFilterValues) => void;
  periodStart: string;
  periodEnd: string;
  onOpenColumnSettings: () => void;
}

const DETAIL_DEPTH_LABELS: Record<DetailDepth, string> = {
  employees: 'Сотрудники',
  tasks: 'Задачи',
  worklogs: 'Ворклоги',
};

function fmtHours(value: number): string {
  return `${value.toFixed(1)} ч`;
}

function fmtPercent(value: number | null | undefined): string {
  return value == null ? '—' : `${value.toFixed(0)}%`;
}

function initials(name: string): string {
  const parts = name.split(/\s+/).filter(Boolean);
  if (!parts.length) return '??';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
}

function stripKeyPrefix(summary: string, key: string): string {
  const trimmed = summary.trim();
  if (trimmed.startsWith(key)) {
    return trimmed.slice(key.length).replace(/^[\s:.\-—]+/, '');
  }
  return trimmed;
}

function categoryMarker(category: AnalyticsCategoryNode): string {
  const words = category.label.split(/\s+/).filter(Boolean);
  if (!words.length) return 'C';
  return words.length === 1
    ? words[0].slice(0, 1).toUpperCase()
    : `${words[0][0]}${words[1][0]}`.toUpperCase();
}

function buildCategoryRows(
  category: AnalyticsCategoryNode,
  prefix: string,
  rows: DetailRow[],
): void {
  const categoryKey = `${prefix}/category:${category.category_code ?? 'none'}`;
  rows.push({
    key: categoryKey,
    depth: 4,
    kind: 'category',
    label: category.label,
    marker: categoryMarker(category),
    markerColor: category.color,
    totals: category.totals,
  });

  for (const issue of category.issues) {
    rows.push({
      key: `${categoryKey}/issue:${issue.id}`,
      depth: 5,
      kind: 'issue',
      label: stripKeyPrefix(issue.summary, issue.key),
      marker: '•',
      totals: issue.totals,
      issue,
      status: issue.status,
      statusCategory: issue.status_category,
    });
  }
}

function buildWorkTypeRows(
  workType: AnalyticsWorkTypeNode,
  prefix: string,
  rows: DetailRow[],
): void {
  const workTypeKey = `${prefix}/work-type:${workType.work_type_id}`;
  rows.push({
    key: workTypeKey,
    depth: 3,
    kind: 'workType',
    label: workType.label,
    marker: 'W',
    totals: workType.totals,
  });

  for (const category of workType.categories) {
    buildCategoryRows(category, workTypeKey, rows);
  }
}

function buildEmployeeRows(
  employee: AnalyticsEmployeeNode,
  prefix: string,
  rows: DetailRow[],
): void {
  const employeeKey = `${prefix}/employee:${employee.employee_id}`;
  rows.push({
    key: employeeKey,
    depth: 2,
    kind: 'employee',
    label: employee.name,
    marker: employee.initials || initials(employee.name),
    totals: employee.totals,
  });

  for (const workType of employee.work_types) {
    buildWorkTypeRows(workType, employeeKey, rows);
  }
}

function buildRoleRows(role: AnalyticsRoleNode, prefix: string, rows: DetailRow[]): void {
  const roleKey = `${prefix}/role:${role.role_code ?? 'none'}`;
  rows.push({
    key: roleKey,
    depth: 1,
    kind: 'role',
    label: role.role_label,
    marker: initials(role.role_label).slice(0, 2),
    markerColor: role.role_color,
    totals: role.totals,
  });

  for (const employee of role.employees) {
    buildEmployeeRows(employee, roleKey, rows);
  }
}

function buildTeamRows(team: AnalyticsTeamNode): DetailRow[] {
  const rows: DetailRow[] = [];
  const teamKey = `team:${team.team ?? 'none'}`;
  rows.push({
    key: teamKey,
    depth: 0,
    kind: 'team',
    label: team.team || 'Без команды',
    marker: 'T',
    totals: team.totals,
  });

  for (const role of team.roles) {
    buildRoleRows(role, teamKey, rows);
  }
  return rows;
}

function visibleByDepth(row: DetailRow, detailDepth: DetailDepth): boolean {
  if (detailDepth === 'employees') return row.depth <= 2;
  return true;
}

function findFirstIssue(rows: DetailRow[]): AnalyticsIssueNode | undefined {
  return rows.find((row) => row.kind === 'issue')?.issue;
}

function AnalyticsDetailInspector({
  issueId,
  periodStart,
  periodEnd,
  onSelectIssue,
}: {
  issueId: string | null;
  periodStart: string;
  periodEnd: string;
  onSelectIssue: (issueId: string) => void;
}) {
  const queryClient = useQueryClient();
  const { data: context, isLoading, isError, refetch } = useIssueContext(issueId);
  const { items: categories } = useCategories();

  const goals = useMemo(
    () => context?.goals?.split(',').map((item) => item.trim()).filter(Boolean) ?? [],
    [context?.goals],
  );

  if (!issueId) {
    return (
      <aside className="analytics-detail-panel analytics-detail-inspector">
        <div className="analytics-detail-panel-head">
          <div className="analytics-detail-panel-title">Детализация задачи</div>
          <div className="analytics-detail-panel-subtitle">Выберите задачу в таблице</div>
        </div>
        <div className="analytics-detail-empty">
          <Empty description="Задача не выбрана" />
        </div>
      </aside>
    );
  }

  if (isLoading) {
    return (
      <aside className="analytics-detail-panel analytics-detail-inspector">
        <div className="analytics-detail-panel-head">
          <div className="analytics-detail-panel-title">Детализация задачи</div>
          <div className="analytics-detail-panel-subtitle">Загрузка контекста</div>
        </div>
        <div className="analytics-detail-inspector-body">
          <Skeleton active paragraph={{ rows: 8 }} />
        </div>
      </aside>
    );
  }

  if (isError || !context) {
    return (
      <aside className="analytics-detail-panel analytics-detail-inspector">
        <div className="analytics-detail-panel-head">
          <div className="analytics-detail-panel-title">Детализация задачи</div>
          <div className="analytics-detail-panel-subtitle">Контекст не загрузился</div>
        </div>
        <div className="analytics-detail-empty">
          <Empty description="Не удалось загрузить задачу" />
          <Button onClick={() => refetch()}>Повторить</Button>
        </div>
      </aside>
    );
  }

  const handleDrillDown = (nextIssueId: string) => {
    onSelectIssue(nextIssueId);
  };

  const handleSaved = () => {
    queryClient.invalidateQueries({ queryKey: ['analytics-report'] });
  };

  return (
    <aside className="analytics-detail-panel analytics-detail-inspector">
      <div className="analytics-detail-panel-head">
        <div className="analytics-detail-inspector-title">
          <div>
            <div className="analytics-detail-panel-title">Детализация задачи</div>
            <div className="analytics-detail-panel-subtitle">Контекст, категории и списания</div>
          </div>
          <Button
            size="small"
            href={`https://example.atlassian.net/browse/${context.key}`}
            target="_blank"
          >
            В Jira
          </Button>
        </div>
      </div>

      <div className="analytics-detail-inspector-body">
        <div>
          <div className="analytics-detail-inspector-key">{context.key}</div>
          <div className="analytics-detail-inspector-summary">{context.summary}</div>
          <div className="analytics-detail-inspector-meta">
            <Tag color={statusTagColor(context.status, context.status_category)}>
              {context.status}
            </Tag>
            <Tag>{context.issue_type}</Tag>
            {context.assigned_category ? <Tag color="cyan">Категория задана</Tag> : <Tag>Категория унаследована</Tag>}
            {context.is_container && <Tag color="gold">Контейнер</Tag>}
          </div>
        </div>

        <div className="analytics-detail-section">
          <div className="analytics-detail-section-head">
            <span>Описание и цели</span>
          </div>
          <div className="analytics-detail-section-body">
            {context.description || 'Описание не заполнено.'}
            {goals.length > 0 && (
              <div className="analytics-detail-goals">
                {goals.map((goal) => (
                  <span className="analytics-detail-goal" key={goal}>
                    {goal}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>

        <IssueContextBlock
          context={context}
          categories={categories}
          onDrillDown={handleDrillDown}
          onChildSaved={handleSaved}
        />

        <IssueCategorizer
          context={context}
          categories={categories}
          onSaved={handleSaved}
        />

        <div className="analytics-detail-section">
          <div className="analytics-detail-section-head">
            <span>Ворклоги за период</span>
            <span className="analytics-detail-muted">{periodStart} - {periodEnd}</span>
          </div>
          <AnalyticsWorklogsBlock
            issueId={context.id}
            periodStart={periodStart}
            periodEnd={periodEnd}
          />
        </div>
      </div>
    </aside>
  );
}

export default function AnalyticsDetailWorkspace({
  data,
  selectedTeam,
  onSelectTeam,
  urlParams,
  onFilterChange,
  periodStart,
  periodEnd,
  onOpenColumnSettings,
}: Props) {
  const [detailDepth, setDetailDepth] = useState<DetailDepth>('tasks');
  const [selectedIssueId, setSelectedIssueId] = useState<string | null>(null);
  const { visible } = useAnalyticsColumns();
  const { data: employees = [] } = useEmployeesForFilter();
  const { items: categories } = useCategories();
  const { data: workTypes = [] } = useMandatoryWorkTypes();

  const teams = useMemo(
    () =>
      selectedTeam === 'all'
        ? data.teams
        : data.teams.filter((team) => (team.team || '_none_') === selectedTeam),
    [data.teams, selectedTeam],
  );

  const rows = useMemo(
    () =>
      teams
        .flatMap(buildTeamRows)
        .filter((row) => visibleByDepth(row, detailDepth)),
    [detailDepth, teams],
  );

  const activeIssueId = useMemo(() => {
    if (selectedIssueId && rows.some((row) => row.issue?.id === selectedIssueId)) {
      return selectedIssueId;
    }
    return findFirstIssue(rows)?.id ?? null;
  }, [rows, selectedIssueId]);

  const visibleSet = useMemo(() => new Set(visible), [visible]);
  const visibleColumns = {
    plan: visibleSet.has('plan_hours'),
    pctPlan: visibleSet.has('pct_plan'),
    pctTotal: visibleSet.has('pct_total'),
    worklogs: visibleSet.has('worklog_count'),
    issues: visibleSet.has('issue_count'),
    employees: visibleSet.has('employee_count'),
    avg: visibleSet.has('avg_worklog_minutes'),
  };

  const employeeOptions = employees.map((employee) => ({
    value: employee.id,
    label: employee.display_name,
  }));
  const categoryOptions = categories.map((category) => ({
    value: category.code,
    label: category.label,
  }));
  const workTypeOptions = workTypes.map((workType) => ({
    value: workType.code,
    label: workType.label,
  }));

  return (
    <div className="analytics-detail-workspace">
      <aside className="analytics-detail-panel">
        <div className="analytics-detail-panel-head">
          <div className="analytics-detail-panel-title">Команды</div>
          <div className="analytics-detail-panel-subtitle">Быстрый переход между срезами</div>
        </div>
        <div className="analytics-detail-team-list">
          <div
            className={`analytics-detail-team-row ${selectedTeam === 'all' ? 'is-active' : ''}`}
            onClick={() => onSelectTeam('all')}
          >
            <span className="analytics-detail-team-name">Все команды</span>
            <span className="analytics-detail-team-hours">{fmtHours(data.grand_totals.fact_hours)}</span>
          </div>
          {data.teams.map((team) => {
            const value = team.team || '_none_';
            const isActive = selectedTeam === value || (selectedTeam === 'all' && false);
            return (
              <div
                className={`analytics-detail-team-row ${isActive ? 'is-active' : ''}`}
                key={value}
                onClick={() => onSelectTeam(value)}
              >
                <span className="analytics-detail-team-name">{team.team || 'Без команды'}</span>
                <span className="analytics-detail-team-hours">{fmtHours(team.totals.fact_hours)}</span>
              </div>
            );
          })}
        </div>
      </aside>

      <section className="analytics-detail-panel">
        <div className="analytics-detail-filters">
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="Сотрудник"
            options={employeeOptions}
            value={urlParams.employeeId ?? null}
            onChange={(value) => onFilterChange({ ...urlParams, employeeId: value ?? undefined })}
          />
          <Input.Search
            placeholder="Поиск по ключу или названию задачи"
            defaultValue={urlParams.taskQ}
            onSearch={(value) => onFilterChange({ ...urlParams, taskQ: value || undefined })}
          />
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="Вид работ"
            options={workTypeOptions}
            value={urlParams.workType ?? null}
            onChange={(value) => onFilterChange({ ...urlParams, workType: value ?? undefined })}
          />
          <Select
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="Категория"
            options={categoryOptions}
            value={urlParams.category ?? null}
            onChange={(value) => onFilterChange({ ...urlParams, category: value ?? undefined })}
          />
          <Segmented
            value={detailDepth}
            onChange={(value) => setDetailDepth(value as DetailDepth)}
            options={Object.entries(DETAIL_DEPTH_LABELS).map(([value, label]) => ({ value, label }))}
          />
          <Button icon={<SettingOutlined />} onClick={onOpenColumnSettings}>
            Столбцы
          </Button>
        </div>

        <div className="analytics-detail-table-wrap">
          {rows.length === 0 ? (
            <div className="analytics-detail-empty">
              <Empty description="Нет строк для выбранного среза" />
            </div>
          ) : (
            <table className="analytics-detail-table">
              <thead>
                <tr>
                  <th>Группа / задача</th>
                  <th className="analytics-detail-number">Факт</th>
                  {visibleColumns.plan && <th className="analytics-detail-number">План</th>}
                  {visibleColumns.pctPlan && <th className="analytics-detail-number">% план</th>}
                  {visibleColumns.pctTotal && <th className="analytics-detail-number">% итога</th>}
                  {visibleColumns.worklogs && <th className="analytics-detail-number">Ворклоги</th>}
                  {visibleColumns.issues && <th className="analytics-detail-number">Задачи</th>}
                  {visibleColumns.employees && <th className="analytics-detail-number">Сотр.</th>}
                  {visibleColumns.avg && <th className="analytics-detail-number">Ср. мин</th>}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const isIssue = row.kind === 'issue';
                  const selected = isIssue && row.issue?.id === activeIssueId;
                  return (
                    <tr
                      className={[
                        'analytics-detail-row',
                        !isIssue ? 'is-group' : '',
                        isIssue ? 'is-clickable' : '',
                        selected ? 'is-selected' : '',
                      ].filter(Boolean).join(' ')}
                      key={row.key}
                      onClick={() => {
                        if (row.issue) setSelectedIssueId(row.issue.id);
                      }}
                    >
                      <td>
                        <div className={`analytics-detail-label depth-${Math.min(row.depth, 4)}`}>
                          <span
                            className={`analytics-detail-marker ${isIssue ? 'issue' : row.kind}`}
                            style={row.markerColor ? { background: row.markerColor } : undefined}
                          >
                            {row.marker}
                          </span>
                          {isIssue && row.issue && (
                            <span className="analytics-detail-label-key">{row.issue.key}</span>
                          )}
                          {isIssue && row.status && (
                            <Tag
                              className="analytics-detail-status"
                              color={statusTagColor(row.status, row.statusCategory)}
                            >
                              {row.status}
                            </Tag>
                          )}
                          {row.issue?.is_foreign && (
                            <Tag className="analytics-detail-status" color="orange">
                              Чужая
                            </Tag>
                          )}
                          <span className="analytics-detail-label-main">{row.label}</span>
                        </div>
                      </td>
                      <td className="analytics-detail-number fact">{fmtHours(row.totals.fact_hours)}</td>
                      {visibleColumns.plan && (
                        <td className="analytics-detail-number analytics-detail-muted">
                          {row.totals.plan_hours == null ? '—' : fmtHours(row.totals.plan_hours)}
                        </td>
                      )}
                      {visibleColumns.pctPlan && (
                        <td className="analytics-detail-number analytics-detail-muted">
                          {fmtPercent(row.totals.pct_plan)}
                        </td>
                      )}
                      {visibleColumns.pctTotal && (
                        <td className="analytics-detail-number">
                          <span className="analytics-detail-share">
                            <span>{row.totals.pct_total.toFixed(1)}%</span>
                            <span className="analytics-detail-share-bar">
                              <span style={{ width: `${Math.min(100, row.totals.pct_total)}%` }} />
                            </span>
                          </span>
                        </td>
                      )}
                      {visibleColumns.worklogs && (
                        <td className="analytics-detail-number">{row.totals.worklog_count}</td>
                      )}
                      {visibleColumns.issues && (
                        <td className="analytics-detail-number">{row.totals.issue_count}</td>
                      )}
                      {visibleColumns.employees && (
                        <td className="analytics-detail-number">{row.totals.employee_count}</td>
                      )}
                      {visibleColumns.avg && (
                        <td className="analytics-detail-number">
                          {row.totals.avg_worklog_minutes.toFixed(0)}
                        </td>
                      )}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </section>

      <AnalyticsDetailInspector
        issueId={activeIssueId}
        periodStart={periodStart}
        periodEnd={periodEnd}
        onSelectIssue={setSelectedIssueId}
      />
    </div>
  );
}
