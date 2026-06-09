import type React from 'react';
import { useEffect, useMemo, useState } from 'react';
import { Button, Table, Tag, Tooltip } from 'antd';
import { ArrowRightOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router';
import { useGlobalPeriod } from '../../hooks/useGlobalPeriod';
import { useGlobalTeamFilter } from '../../hooks/useGlobalTeamFilter';
import type { ColumnsType } from 'antd/es/table/interface';
import type { Key } from 'react';
import type {
  AnalyticsReportResponse,
  NodeTotals,
  AnalyticsIssueNode,
} from '../../types/api';
import { useAnalyticsColumns } from '../../hooks/useAnalyticsColumns';
import { useAnalyticsLayout } from '../../hooks/useAnalyticsLayout';
import type { AnalyticsLevel } from '../../hooks/useAnalyticsLayout';
import { statusTagColor } from '../../utils/status';
import AnalyticsWorklogsBlock from './AnalyticsWorklogsBlock';
import AnalyticsIssueDrawer from './AnalyticsIssueDrawer';

type RowKind = 'team' | 'role' | 'emp' | 'wt' | 'cat' | 'issue' | 'worklog-block';

interface TreeNode {
  key: string;
  kind: RowKind;
  depth: number;
  label: React.ReactNode;
  totals: NodeTotals;
  children?: TreeNode[];
  /** Issue UUID — set only for issue rows */
  issueId?: string;
  /** Issue Jira key (e.g. PROJ-123) — set only for issue rows */
  issueKey?: string;
}

const EMPTY_TOTALS: NodeTotals = {
  fact_hours: 0,
  plan_hours: null,
  pct_plan: null,
  pct_total: 0,
  pct_in_group: null,
  worklog_count: 0,
  issue_count: 0,
  employee_count: 0,
  avg_worklog_minutes: 0,
  foreign_issue_count: 0,
  foreign_hours: 0,
  foreign_pct: 0,
};

function initialsOf(name: string): string {
  const parts = (name || '').split(/\s+/).filter(Boolean);
  if (!parts.length) return '??';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

function indent(depth: number, content: React.ReactNode): React.ReactNode {
  return (
    <div style={{ paddingLeft: depth * 14, lineHeight: 1.35 }}>{content}</div>
  );
}

function pctColor(pct: number | null | undefined): string | undefined {
  if (pct == null) return undefined;
  if (pct > 110) return '#ff4d4f';
  if (pct >= 70) return '#faad14';
  return '#67d68d';
}

function stripKeyPrefix(summary: string, key: string): string {
  // Некоторые Jira-summary включают ключ в начало («OS-79306 Обмен Розница...»).
  // Срезаем чтобы не дублировалось со ссылкой-ключом слева.
  const trimmed = summary.trim();
  if (trimmed.startsWith(key)) {
    return trimmed.slice(key.length).replace(/^[\s:.\-—]+/, '');
  }
  return trimmed;
}

const TEAM_COLOR_PALETTE = [
  '#9c6bff', '#22d3ee', '#f97316', '#10b981',
  '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4',
];

function teamColor(name: string | null | undefined): string {
  if (!name) return 'var(--text-muted, #7e94b8)';
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0;
  return TEAM_COLOR_PALETTE[Math.abs(h) % TEAM_COLOR_PALETTE.length];
}

function buildIssueNode(
  i: AnalyticsIssueNode,
  prefix: string,
  depth: number,
  worklogMode: 'inline' | 'drawer',
  periodStart: string,
  periodEnd: string,
  navigate: ReturnType<typeof useNavigate>,
): TreeNode {
  const cleanSummary = stripKeyPrefix(i.summary, i.key);
  const isProject =
    i.category === 'quarterly_tasks' || i.category === 'archive_target';
  const node: TreeNode = {
    key: `${prefix}/i:${i.id}`,
    kind: 'issue',
    depth,
    issueId: i.id,
    issueKey: i.key,
    label: indent(
      depth,
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-start',
            gap: 6,
            minWidth: 0,
          }}
        >
          <a
            href={`https://itgri.atlassian.net/browse/${i.key}`}
            target="_blank"
            rel="noreferrer"
            onClick={(e) => e.stopPropagation()}
            style={{
              color: '#22d3ee',
              textDecoration: 'underline',
              fontWeight: 600,
              flexShrink: 0,
              whiteSpace: 'nowrap',
            }}
          >
            {i.key}
          </a>
          <Tag
            color={statusTagColor(i.status, i.status_category)}
            style={{ marginInlineEnd: 0, flexShrink: 0 }}
          >
            {i.status}
          </Tag>
          {i.is_foreign && (
            <Tag
              color="orange"
              style={{ marginInlineEnd: 0, flexShrink: 0 }}
              title="Задача чужой команды (списание часов вне scope сотрудника)"
            >
              Чужая
            </Tag>
          )}
          <span
            style={{
              color: 'var(--text, #e6edf7)',
              whiteSpace: 'normal',
              wordBreak: 'break-word',
              minWidth: 0,
              flex: '1 1 auto',
            }}
          >
            {cleanSummary}
          </span>
          {isProject && (
            <Button
              size="small"
              type="link"
              icon={<ArrowRightOutlined />}
              onClick={(e) => {
                e.stopPropagation();
                navigate(`/projects/${encodeURIComponent(i.key)}`);
              }}
              title="Открыть страницу проекта"
              style={{ flexShrink: 0, padding: '0 4px' }}
            />
          )}
        </div>
        {i.is_foreign && i.team && (
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              fontSize: 11,
              color: 'var(--text-muted, #7e94b8)',
              paddingLeft: 2,
            }}
          >
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: 2,
                background: teamColor(i.team),
                display: 'inline-block',
                flexShrink: 0,
              }}
            />
            <span>Команда: <span style={{ color: teamColor(i.team) }}>{i.team}</span></span>
          </div>
        )}
      </div>,
    ),
    totals: i.totals,
  };

  // В inline-режиме ворклоги задачи показываются как один child-row через
  // tree-expansion, чтобы не конфликтовать с tree-mode на родительских уровнях.
  if (worklogMode === 'inline') {
    node.children = [
      {
        key: `${node.key}/wl`,
        kind: 'worklog-block',
        depth: depth + 1,
        label: (
          <div style={{ paddingLeft: (depth + 1) * 14 }}>
            <AnalyticsWorklogsBlock
              issueId={i.id}
              periodStart={periodStart}
              periodEnd={periodEnd}
            />
          </div>
        ),
        totals: EMPTY_TOTALS,
      },
    ];
  }

  return node;
}

function ForeignChip({ totals }: { totals: NodeTotals }) {
  if (!totals.foreign_issue_count || totals.foreign_issue_count === 0) return null;
  return (
    <Tooltip title={`Чужие задачи под этим узлом: ${totals.foreign_issue_count} зад. · ${totals.foreign_hours.toFixed(1)}ч · ${totals.foreign_pct.toFixed(1)}% от факта`}>
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 4,
          marginLeft: 8,
          padding: '2px 8px',
          borderRadius: 999,
          fontSize: 11,
          fontWeight: 600,
          background: 'rgba(255, 156, 74, 0.12)',
          color: '#ff9c4a',
          border: '1px solid rgba(255, 156, 74, 0.35)',
        }}
      >
        ⚠ {totals.foreign_issue_count} · {totals.foreign_hours.toFixed(0)}ч · {totals.foreign_pct.toFixed(0)}%
      </span>
    </Tooltip>
  );
}

// ─── Flat-row extraction ──────────────────────────────────────────────────────

interface FlatRow {
  team: string;
  team_label: string;
  role: string | null;
  role_label: string;
  role_color: string;
  employee_id: string;
  employee_name: string;
  employee_initials: string;
  work_type_id: string;
  work_type_label: string;
  category_code: string | null;
  category_label: string;
  category_color: string;
  issue: AnalyticsIssueNode;
}

function flattenResponse(data: AnalyticsReportResponse): FlatRow[] {
  const out: FlatRow[] = [];
  for (const t of data.teams) {
    const teamKey = t.team ?? '__no_team__';
    const teamLabel = t.team ?? 'Без команды';
    for (const r of t.roles) {
      for (const e of r.employees) {
        for (const w of e.work_types) {
          for (const c of w.categories) {
            for (const i of c.issues) {
              out.push({
                team: teamKey,
                team_label: teamLabel,
                role: r.role_code,
                role_label: r.role_label,
                role_color: r.role_color,
                employee_id: e.employee_id,
                employee_name: e.name,
                employee_initials: e.initials,
                work_type_id: w.work_type_id,
                work_type_label: w.label,
                category_code: c.category_code,
                category_label: c.label,
                category_color: c.color,
                issue: i,
              });
            }
          }
        }
      }
    }
  }
  return out;
}

function keyOf(level: AnalyticsLevel, row: FlatRow): string {
  switch (level) {
    case 'team': return row.team;
    case 'role': return `${row.team}|${row.role ?? '_none'}`;
    case 'employee': return row.employee_id;
    case 'work_type': return row.work_type_id;
    case 'category': return row.category_code ?? '_none';
    case 'issue': return row.issue.id;
  }
}

function aggregateTotals(
  rows: FlatRow[],
  parentFact: number | null,
  grandFact: number,
  planByEmpWt: Map<string, number>,
): NodeTotals {
  const fact = rows.reduce((s, r) => s + r.issue.totals.fact_hours, 0);
  const issueIds = new Set(rows.map((r) => r.issue.id));
  const empIds = new Set(rows.map((r) => r.employee_id));
  const foreignRows = rows.filter((r) => r.issue.is_foreign);
  const foreignHours = foreignRows.reduce((s, r) => s + r.issue.totals.fact_hours, 0);
  const foreignIssues = new Set(foreignRows.map((r) => r.issue.id));
  const wl = rows.reduce((s, r) => s + r.issue.totals.worklog_count, 0);

  const planKeys = new Set<string>();
  for (const r of rows) planKeys.add(`${r.employee_id}|${r.work_type_id}`);
  let plan = 0;
  let havePlan = false;
  for (const k of planKeys) {
    const p = planByEmpWt.get(k);
    if (p != null) { plan += p; havePlan = true; }
  }
  const planHours = havePlan && plan > 0 ? Math.round(plan * 10) / 10 : null;
  const pctPlan = planHours != null && planHours > 0
    ? Math.round((fact / planHours) * 1000) / 10
    : null;

  return {
    fact_hours: Math.round(fact * 10) / 10,
    plan_hours: planHours,
    pct_plan: pctPlan,
    pct_total: grandFact > 0 ? Math.round((fact / grandFact) * 1000) / 10 : 0,
    pct_in_group: parentFact && parentFact > 0 ? Math.round((fact / parentFact) * 1000) / 10 : null,
    worklog_count: wl,
    issue_count: issueIds.size,
    employee_count: empIds.size,
    avg_worklog_minutes: wl > 0 ? Math.round((fact * 60 / wl) * 10) / 10 : 0,
    foreign_issue_count: foreignIssues.size,
    foreign_hours: Math.round(foreignHours * 10) / 10,
    foreign_pct: fact > 0 ? Math.round((foreignHours / fact) * 1000) / 10 : 0,
  };
}

function kindOfLevel(level: AnalyticsLevel): RowKind {
  switch (level) {
    case 'team': return 'team';
    case 'role': return 'role';
    case 'employee': return 'emp';
    case 'work_type': return 'wt';
    case 'category': return 'cat';
    case 'issue': return 'issue';
  }
}

function buildTreeFromLayout(
  data: AnalyticsReportResponse,
  layout: AnalyticsLevel[],
  worklogMode: 'inline' | 'drawer',
  periodStart: string,
  periodEnd: string,
  navigate: ReturnType<typeof useNavigate>,
  thematicParams: URLSearchParams | null,
): TreeNode[] {
  const flat = flattenResponse(data);
  const grandFact = flat.reduce((s, r) => s + r.issue.totals.fact_hours, 0);

  const planByEmpWt = new Map<string, number>();
  for (const t of data.teams) {
    for (const r of t.roles) {
      for (const e of r.employees) {
        for (const w of e.work_types) {
          if (w.totals.plan_hours != null) {
            planByEmpWt.set(`${e.employee_id}|${w.work_type_id}`, w.totals.plan_hours);
          }
        }
      }
    }
  }

  function labelOf(level: AnalyticsLevel, row: FlatRow, depth: number): React.ReactNode {
    switch (level) {
      case 'team':
        return indent(depth, <b>{row.team_label}</b>);
      case 'role':
        return indent(
          depth,
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <span
              style={{
                display: 'inline-block',
                width: 10,
                height: 10,
                borderRadius: '50%',
                background: row.role_color,
                flexShrink: 0,
              }}
            />
            <span style={{ color: row.role_color, fontWeight: 600 }}>
              {row.role_label}
            </span>
          </span>,
        );
      case 'employee': {
        const initials = row.employee_initials || initialsOf(row.employee_name);
        return indent(
          depth,
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 22,
                height: 22,
                borderRadius: '50%',
                background: row.role_color,
                color: '#fff',
                fontSize: 10,
                fontWeight: 700,
                flexShrink: 0,
              }}
            >
              {initials}
            </span>
            <span style={{ color: 'var(--text, #e6edf7)' }}>{row.employee_name}</span>
          </span>,
        );
      }
      case 'work_type': {
        const thematicUrl = thematicParams
          ? `/analytics/work-type-report?${new URLSearchParams({
              ...Object.fromEntries(thematicParams),
              work_type_id: row.work_type_id,
            }).toString()}`
          : null;
        return indent(
          depth,
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <span
              style={{
                display: 'inline-block',
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: 'var(--text-muted, #7e94b8)',
                flexShrink: 0,
              }}
            />
            <span style={{ fontWeight: 500 }}>{row.work_type_label}</span>
            {thematicUrl && (
              <Tooltip title="Тематический отчёт">
                <Button
                  type="link"
                  size="small"
                  icon={<ArrowRightOutlined />}
                  style={{ padding: '0 2px', height: 'auto', color: '#00c9c8', marginLeft: 2 }}
                  onClick={(e) => {
                    e.stopPropagation();
                    navigate(thematicUrl);
                  }}
                />
              </Tooltip>
            )}
          </span>,
        );
      }
      case 'category':
        return indent(
          depth,
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            <span
              style={{
                display: 'inline-block',
                width: 10,
                height: 10,
                borderRadius: '50%',
                background: row.category_color,
                flexShrink: 0,
              }}
            />
            <span>{row.category_label}</span>
          </span>,
        );
      case 'issue':
        throw new Error('issue is a leaf, not a group level');
    }
  }

  function group(
    rows: FlatRow[],
    levels: AnalyticsLevel[],
    depth: number,
    keyPrefix: string,
    parentFact: number | null,
  ): TreeNode[] {
    if (rows.length === 0) return [];
    if (levels.length === 0) return [];
    const [head, ...rest] = levels;

    if (head === 'issue') {
      // Aggregate by issue.id (a single issue may appear multiple times if a
      // grouping dimension was collapsed above it).
      const byId = new Map<string, FlatRow[]>();
      for (const r of rows) {
        const arr = byId.get(r.issue.id) ?? [];
        arr.push(r);
        byId.set(r.issue.id, arr);
      }
      const nodes: TreeNode[] = [];
      for (const [, grp] of byId.entries()) {
        const sample = grp[0];
        const totals = aggregateTotals(grp, parentFact, grandFact, planByEmpWt);
        const issueLikeRow: AnalyticsIssueNode = { ...sample.issue, totals };
        const node = buildIssueNode(
          issueLikeRow,
          keyPrefix,
          depth,
          worklogMode,
          periodStart,
          periodEnd,
          navigate,
        );
        nodes.push(node);
      }
      return nodes.sort((a, b) => b.totals.fact_hours - a.totals.fact_hours);
    }

    // Group rows by the current level key
    const groups = new Map<string, FlatRow[]>();
    for (const r of rows) {
      const k = keyOf(head, r);
      const arr = groups.get(k) ?? [];
      arr.push(r);
      groups.set(k, arr);
    }

    const nodes: TreeNode[] = [];
    for (const [k, rs] of groups.entries()) {
      const sample = rs[0];
      const totals = aggregateTotals(rs, parentFact, grandFact, planByEmpWt);
      const nodeKey = `${keyPrefix}/${head}:${k}`;
      const children = group(rs, rest, depth + 1, nodeKey, totals.fact_hours);
      nodes.push({
        key: nodeKey,
        kind: kindOfLevel(head),
        depth,
        label: labelOf(head, sample, depth),
        totals,
        children: children.length > 0 ? children : undefined,
      });
    }
    return nodes.sort((a, b) => b.totals.fact_hours - a.totals.fact_hours);
  }

  return group(flat, layout, 0, 'root', grandFact);
}

// ─── Component ────────────────────────────────────────────────────────────────

interface Props {
  data: AnalyticsReportResponse;
  selectedTeam: string | 'all';
  worklogMode: 'inline' | 'drawer';
  periodStart: string;
  periodEnd: string;
}

export default function AnalyticsTable({
  data,
  selectedTeam,
  worklogMode,
  periodStart,
  periodEnd,
}: Props) {
  const { visible } = useAnalyticsColumns();
  const visibleSet = new Set(visible);
  const navigate = useNavigate();
  const { period } = useGlobalPeriod();
  const { selectedTeams } = useGlobalTeamFilter();
  const [drawerIssue, setDrawerIssue] = useState<{ id: string; key: string } | null>(null);
  const { resolved } = useAnalyticsLayout();

  // Params for thematic report deep-links (work_type_id is added per-row)
  const thematicBaseParams = new URLSearchParams({
    year: String(period.year),
    quarter: String(period.quarter),
    ...(period.month != null ? { month: String(period.month) } : {}),
    ...(selectedTeams.length > 0 ? { teams: selectedTeams.join(',') } : {}),
  });

  const expandedStorageKey = `analytics-tree-expanded:${selectedTeam}`;
  const [expandedRowKeys, setExpandedRowKeys] = useState<readonly Key[]>(() => {
    try {
      const raw = localStorage.getItem(expandedStorageKey);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  });

  useEffect(() => {
    try {
      const raw = localStorage.getItem(expandedStorageKey);
      const parsed = raw ? JSON.parse(raw) : [];
      setExpandedRowKeys(Array.isArray(parsed) ? parsed : []);
    } catch {
      setExpandedRowKeys([]);
    }
  }, [expandedStorageKey]);

  useEffect(() => {
    try {
      localStorage.setItem(expandedStorageKey, JSON.stringify(expandedRowKeys));
    } catch {
      /* storage недоступен — ок */
    }
  }, [expandedRowKeys, expandedStorageKey]);

  const filteredData: AnalyticsReportResponse = useMemo(() => {
    if (selectedTeam === 'all') return data;
    return {
      ...data,
      teams: data.teams.filter((t) => (t.team || '_none_') === selectedTeam),
    };
  }, [data, selectedTeam]);

  const layout = useMemo(() => {
    let levels = resolved.visibleLevels;
    if (selectedTeam !== 'all') {
      // when a single team is selected, drop 'team' from grouping (single value anyway)
      levels = levels.filter((l) => l !== 'team');
    }
    if (!levels.includes('issue')) levels = [...levels, 'issue'];
    return levels;
  }, [resolved.visibleLevels, selectedTeam]);

  const tableData: TreeNode[] = useMemo(
    () =>
      buildTreeFromLayout(
        filteredData,
        layout,
        worklogMode,
        periodStart,
        periodEnd,
        navigate,
        thematicBaseParams,
      ),
    // thematicBaseParams is recreated each render but is URLSearchParams — stable via stringification
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [filteredData, layout, worklogMode, periodStart, periodEnd, navigate],
  );

  const isBlock = (r: TreeNode) => r.kind === 'worklog-block';

  const allColumns: ColumnsType<TreeNode> = [
    {
      title: 'Группа / Задача',
      dataIndex: 'label',
      key: 'label',
      width: 600,
      ellipsis: false,
    },
    {
      title: 'Часы факт',
      key: 'fact_hours',
      render: (_, r) => {
        if (isBlock(r)) return null;
        const pct = r.depth === 0
          ? r.totals.pct_total
          : (r.totals.pct_in_group ?? 0);
        const barWidth = Math.min(100, Math.max(0, pct));
        const showBar = resolved.showFactBar && r.kind !== 'issue';
        return (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 }}>
            <span style={{ display: 'inline-flex', alignItems: 'center' }}>
              <span style={{ color: pctColor(r.totals.pct_plan), fontWeight: 600 }}>
                {r.totals.fact_hours.toFixed(1)}
              </span>
              {r.kind !== 'issue' && <ForeignChip totals={r.totals} />}
            </span>
            {showBar && (
              <div
                style={{
                  width: '100%',
                  height: 3,
                  background: 'rgba(255,255,255,0.06)',
                  borderRadius: 2,
                  overflow: 'hidden',
                }}
              >
                <div
                  style={{
                    width: `${barWidth}%`,
                    height: '100%',
                    background: '#00c9c8',
                    opacity: 0.85,
                  }}
                />
              </div>
            )}
          </div>
        );
      },
      width: 220,
      align: 'right',
    },
    {
      title: 'Часы план',
      key: 'plan_hours',
      render: (_, r) =>
        isBlock(r) ? null : r.totals.plan_hours != null ? Math.round(r.totals.plan_hours) : '—',
      width: 100,
      align: 'right',
    },
    {
      title: '% план',
      key: 'pct_plan',
      render: (_, r) =>
        isBlock(r)
          ? null
          : r.totals.pct_plan != null
            ? (
                <span style={{ color: pctColor(r.totals.pct_plan), fontWeight: 600 }}>
                  {r.totals.pct_plan.toFixed(0)}%
                </span>
              )
            : '—',
      width: 90,
      align: 'right',
    },
    {
      title: '% в группе',
      key: 'pct_in_group',
      render: (_, r) =>
        isBlock(r)
          ? null
          : r.totals.pct_in_group != null
            ? `${r.totals.pct_in_group.toFixed(1)}%`
            : '—',
      width: 100,
      align: 'right',
    },
    {
      title: '% от итога',
      key: 'pct_total',
      render: (_, r) => (isBlock(r) ? null : `${r.totals.pct_total.toFixed(1)}%`),
      width: 100,
      align: 'right',
    },
    {
      title: 'Ворклогов',
      key: 'worklog_count',
      render: (_, r) => (isBlock(r) ? null : r.totals.worklog_count),
      width: 100,
      align: 'right',
    },
    {
      title: 'Задач',
      key: 'issue_count',
      render: (_, r) => (isBlock(r) ? null : r.totals.issue_count),
      width: 80,
      align: 'right',
    },
    {
      title: 'Сотр.',
      key: 'employee_count',
      render: (_, r) => (isBlock(r) ? null : r.totals.employee_count),
      width: 80,
      align: 'right',
    },
    {
      title: 'Ср.мин',
      key: 'avg_min',
      render: (_, r) => (isBlock(r) ? null : r.totals.avg_worklog_minutes.toFixed(0)),
      width: 90,
      align: 'right',
    },
  ];

  // Mandatory columns always shown: label, fact_hours.
  const MANDATORY_KEYS = new Set(['label', 'fact_hours']);
  const columns = allColumns.filter(
    (col) =>
      MANDATORY_KEYS.has(col.key as string) || visibleSet.has(col.key as string),
  );

  return (
    <>
      <Table<TreeNode>
        dataSource={tableData}
        columns={columns}
        rowKey="key"
        pagination={false}
        size="small"
        scroll={{ x: 'max-content' }}
        rowClassName={(record) => {
          const cls = [`tree-row-depth-${record.depth}`];
          if (record.children && record.children.length > 0)
            cls.push('tree-row-has-children');
          return cls.join(' ');
        }}
        expandable={{
          expandedRowKeys,
          onExpandedRowsChange: setExpandedRowKeys,
          expandRowByClick: true,
          rowExpandable: (record) => (record.children?.length ?? 0) > 0,
        }}
        onRow={(record) =>
          worklogMode === 'drawer' && record.kind === 'issue' && record.issueId
            ? {
                onClick: () =>
                  setDrawerIssue({ id: record.issueId!, key: record.issueKey! }),
                style: { cursor: 'pointer' },
              }
            : {}
        }
      />
      <AnalyticsIssueDrawer
        issueId={drawerIssue?.id ?? null}
        issueKey={drawerIssue?.key ?? null}
        periodStart={periodStart}
        periodEnd={periodEnd}
        onClose={() => setDrawerIssue(null)}
      />
    </>
  );
}
