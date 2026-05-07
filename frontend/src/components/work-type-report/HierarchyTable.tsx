import { useEffect, useMemo, useRef, useState } from 'react';
import { Table, Tag } from 'antd';
import type { ColumnsType } from 'antd/es/table/interface';
import type { Key } from 'react';
import { DARK_THEME } from '../../utils/constants';
import ThemeNarrativeRow from './ThemeNarrativeRow';
import type { Theme, ThemeIssue, GroupingDim } from '../../types/workTypeReport';

interface Props {
  themes: Theme[];
  groupingDims: GroupingDim[];
  highlightThemeId?: string | null;
  onIssueClick?: (issueKey: string) => void;
}

// ---- Row kinds ----
type RowKind = 'theme' | 'group' | 'issue';

interface TableRow {
  key: string;
  kind: RowKind;
  label: string;
  hours: number;
  pct: number;
  tasks_count: number;
  employees_count: number;
  // theme-specific
  theme_id?: string | null;
  theme_color?: string;
  theme_is_new?: boolean;
  theme_is_low_confidence?: boolean;
  theme_narrative?: string;
  theme_evidence_keys?: string[];
  // issue-specific
  issue_key?: string;
  issue_summary?: string;
  children?: TableRow[];
}

// Flat issue augmented with theme metadata
interface FlatIssue extends ThemeIssue {
  theme_id: string | null;
  theme_name: string;
  theme_color: string;
  theme_is_new: boolean;
  theme_is_low_confidence: boolean;
  theme_narrative: string;
  theme_evidence_keys: string[];
}

function flattenIssues(themes: Theme[]): FlatIssue[] {
  return themes.flatMap((t) =>
    t.issues.map((i) => ({
      ...i,
      theme_id: t.theme_id,
      theme_name: t.name,
      theme_color: t.color,
      theme_is_new: t.is_new,
      theme_is_low_confidence: t.is_low_confidence ?? false,
      theme_narrative: t.narrative,
      theme_evidence_keys: t.evidence_keys,
    })),
  );
}

// ---- Grouping builders ----

function issueRow(fi: FlatIssue, keyPrefix: string): TableRow {
  return {
    key: `${keyPrefix}/issue:${fi.issue_id}`,
    kind: 'issue',
    label: fi.key,
    hours: fi.hours,
    pct: 0, // computed from totalHours later if needed; not per-issue in theme data
    tasks_count: 1,
    employees_count: fi.employee_breakdown.length,
    issue_key: fi.key,
    issue_summary: fi.summary,
  };
}

function themeRow(theme: Theme, children: TableRow[]): TableRow {
  return {
    key: `theme:${theme.theme_id ?? '_none'}`,
    kind: 'theme',
    label: theme.name,
    hours: theme.totals.hours,
    pct: theme.totals.pct,
    tasks_count: theme.totals.tasks_count,
    employees_count: theme.totals.employees_count,
    theme_id: theme.theme_id,
    theme_color: theme.color,
    theme_is_new: theme.is_new,
    theme_is_low_confidence: theme.is_low_confidence ?? false,
    theme_narrative: theme.narrative,
    theme_evidence_keys: theme.evidence_keys,
    children: children.length > 0 ? children : undefined,
  };
}

// Group issues by a string key-extractor. Returns array of {groupKey, issues}.
function groupBy(
  issues: FlatIssue[],
  keyOf: (fi: FlatIssue) => string,
): { groupKey: string; issues: FlatIssue[] }[] {
  const map = new Map<string, FlatIssue[]>();
  for (const fi of issues) {
    const k = keyOf(fi);
    if (!map.has(k)) map.set(k, []);
    map.get(k)!.push(fi);
  }
  return Array.from(map.entries()).map(([groupKey, issues]) => ({ groupKey, issues }));
}

function sumHours(issues: FlatIssue[]): number {
  return issues.reduce((s, i) => s + i.hours, 0);
}
function sumEmployees(issues: FlatIssue[]): number {
  return new Set(issues.flatMap((i) => i.employee_breakdown.map((e) => e.name))).size;
}

/** Build a simple group row (non-theme) with issue children */
function genericGroupRow(groupKey: string, issues: FlatIssue[], prefix: string): TableRow {
  const rowKey = `${prefix}/${groupKey}`;
  return {
    key: rowKey,
    kind: 'group',
    label: groupKey,
    hours: sumHours(issues),
    pct: 0,
    tasks_count: issues.length,
    employees_count: sumEmployees(issues),
    children: issues.map((fi) => issueRow(fi, rowKey)),
  };
}

// ---- Build table data from dims ----
// MVP: support dims sequences: first dim determines top-level grouping.
// For dims with 'theme' first (default): theme rows → issue rows (+ narrative via expandedRowRender).
// For other top-level dims: group rows → sub-group or issue rows.
// First-employee fallback used for team/role/employee dim (documented below).

function buildRows(themes: Theme[], dims: GroupingDim[], totalHours: number): TableRow[] {
  const flat = flattenIssues(themes);

  const firstDim = dims[0] ?? 'theme';
  const secondDim = dims[1];

  if (firstDim === 'theme') {
    // Default: theme → issues
    return themes.map((t) => {
      const issueChildren = t.issues.map((i) =>
        issueRow(
          {
            ...i,
            theme_id: t.theme_id,
            theme_name: t.name,
            theme_color: t.color,
            theme_is_new: t.is_new,
            theme_is_low_confidence: t.is_low_confidence ?? false,
            theme_narrative: t.narrative,
            theme_evidence_keys: t.evidence_keys,
          },
          `theme:${t.theme_id ?? '_none'}`,
        ),
      );
      return themeRow(t, issueChildren);
    });
  }

  // Non-theme top-level grouping.
  // Fallback: use first entry of employee_breakdown for team/role/employee dims.
  // This means each issue is counted once under its "primary worker".
  // See: intentional MVP simplification — proportional split deferred.

  function dimKey(fi: FlatIssue, dim: GroupingDim): string {
    switch (dim) {
      case 'team':
        return fi.employee_breakdown[0]?.team ?? 'Без команды';
      case 'role':
        return fi.employee_breakdown[0]?.role ?? 'Без роли';
      case 'employee':
        return fi.employee_breakdown[0]?.name ?? 'Неизвестно';
      case 'project':
        return fi.key.split('-')[0] ?? 'Без проекта';
      case 'theme':
        return fi.theme_name;
      case 'issue':
        return fi.key;
    }
  }

  const topGroups = groupBy(flat, (fi) => dimKey(fi, firstDim));

  return topGroups.map(({ groupKey, issues }) => {
    const prefix = `${firstDim}:${groupKey}`;
    let children: TableRow[];

    if (!secondDim || secondDim === 'issue') {
      children = issues.map((fi) => issueRow(fi, prefix));
    } else {
      // Second level grouping — genericGroupRow builds issue children internally
      const subGroups = groupBy(issues, (fi) => dimKey(fi, secondDim));
      children = subGroups.map(({ groupKey: subKey, issues: subIssues }) =>
        genericGroupRow(subKey, subIssues, `${prefix}/${secondDim}`),
      );
    }

    return {
      key: prefix,
      kind: 'group' as RowKind,
      label: groupKey,
      hours: sumHours(issues),
      pct: totalHours > 0 ? (sumHours(issues) / totalHours) * 100 : 0,
      tasks_count: issues.length,
      employees_count: sumEmployees(issues),
      children: children.length > 0 ? children : undefined,
    };
  });
}

// ---- Component ----

export default function HierarchyTable({
  themes,
  groupingDims,
  highlightThemeId,
  onIssueClick,
}: Props) {
  const totalHours = useMemo(
    () => themes.reduce((s, t) => s + t.totals.hours, 0),
    [themes],
  );
  const rows = useMemo(
    () => buildRows(themes, groupingDims, totalHours),
    [themes, groupingDims, totalHours],
  );

  // Default expand top 3 theme/group rows
  const defaultKeys: Key[] = useMemo(() => rows.slice(0, 3).map((r) => r.key), [rows]);
  const [expandedRowKeys, setExpandedRowKeys] = useState<readonly Key[]>(defaultKeys);

  // Highlight: show a CSS pulse on the matched theme row for 2s when highlightThemeId changes.
  // highlightedKey is derived purely from highlightThemeId + expiry state.
  const [highlightExpired, setHighlightExpired] = useState(false);
  const highlightTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Track prev value via ref to detect changes without adding to deps
  const prevHighlightRef = useRef<string | null | undefined>(undefined);

  useEffect(() => {
    if (highlightThemeId == null) return;
    const key = `theme:${highlightThemeId ?? '_none'}`;
    // Ensure the target row is expanded
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setExpandedRowKeys((prev) => (prev.includes(key) ? prev : [...prev, key]));
    if (prevHighlightRef.current !== highlightThemeId) {
      prevHighlightRef.current = highlightThemeId;
      // Reset expiry on new highlight (standard "sync derived state from prop" pattern)
      setHighlightExpired(false);
    }
    if (highlightTimer.current) clearTimeout(highlightTimer.current);
    highlightTimer.current = setTimeout(() => {
      setHighlightExpired(true); // inside async callback — not flagged
    }, 2000);
    return () => {
      if (highlightTimer.current) clearTimeout(highlightTimer.current);
    };
  }, [highlightThemeId]);

  const highlightedKey =
    highlightThemeId != null && !highlightExpired
      ? `theme:${highlightThemeId ?? '_none'}`
      : null;

  const columns: ColumnsType<TableRow> = [
    {
      title: 'Имя',
      key: 'label',
      width: 400,
      render: (_, row) => {
        if (row.kind === 'theme') {
          return (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <span
                style={{
                  display: 'inline-block',
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: row.theme_color,
                  flexShrink: 0,
                }}
              />
              <span style={{ fontWeight: 700, color: DARK_THEME.cyanPrimary }}>{row.label}</span>
              {row.theme_is_new && (
                <Tag color="gold" style={{ marginInlineEnd: 0, fontSize: 11 }}>
                  ★ новая
                </Tag>
              )}
              {row.theme_is_low_confidence && (
                <Tag color="warning" style={{ marginInlineEnd: 0, fontSize: 11 }}>
                  low confidence
                </Tag>
              )}
            </span>
          );
        }
        if (row.kind === 'issue') {
          return (
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
              <a
                style={{ color: DARK_THEME.cyanPrimary, fontWeight: 600, flexShrink: 0 }}
                onClick={() => onIssueClick?.(row.issue_key!)}
              >
                {row.issue_key}
              </a>
              <span
                style={{
                  color: DARK_THEME.textSecondary,
                  fontSize: 12,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
                title={row.issue_summary}
              >
                {row.issue_summary}
              </span>
            </span>
          );
        }
        // group
        return <span style={{ fontWeight: 600, color: DARK_THEME.textPrimary }}>{row.label}</span>;
      },
    },
    {
      title: 'Часы',
      key: 'hours',
      width: 90,
      align: 'right' as const,
      render: (_, row) => (
        <span style={{ color: DARK_THEME.textPrimary }}>{Math.round(row.hours)}</span>
      ),
    },
    {
      title: '% от типа',
      key: 'pct',
      width: 90,
      align: 'right' as const,
      render: (_, row) => {
        const pct =
          row.kind === 'issue'
            ? totalHours > 0
              ? (row.hours / totalHours) * 100
              : 0
            : row.pct;
        return (
          <span style={{ color: DARK_THEME.textMuted }}>{pct.toFixed(1)}%</span>
        );
      },
    },
    {
      title: 'Задач',
      key: 'tasks_count',
      width: 70,
      align: 'right' as const,
      render: (_, row) => (
        <span style={{ color: DARK_THEME.textMuted }}>{row.tasks_count}</span>
      ),
    },
    {
      title: 'Сотруд.',
      key: 'employees_count',
      width: 80,
      align: 'right' as const,
      render: (_, row) => (
        <span style={{ color: DARK_THEME.textMuted }}>{row.employees_count}</span>
      ),
    },
  ];

  return (
    <div
      style={{
        background: DARK_THEME.cardBg,
        border: `1px solid ${DARK_THEME.border}`,
        borderRadius: 8,
        marginBottom: 16,
        overflow: 'hidden',
      }}
    >
      <Table<TableRow>
        dataSource={rows}
        columns={columns}
        rowKey="key"
        pagination={false}
        size="small"
        scroll={{ x: 'max-content' }}
        expandable={{
          expandedRowKeys,
          onExpandedRowsChange: setExpandedRowKeys,
          expandRowByClick: false,
          rowExpandable: (row) => (row.children?.length ?? 0) > 0 || row.kind === 'theme',
          // Narrative row for theme rows rendered via expandedRowRender
          expandedRowRender: (row) => {
            if (row.kind !== 'theme') return null;
            return (
              <ThemeNarrativeRow
                themeId={row.theme_id ?? null}
                narrative={row.theme_narrative ?? ''}
                evidenceKeys={row.theme_evidence_keys ?? []}
                onIssueClick={onIssueClick}
              />
            );
          },
        }}
        rowClassName={(row) => {
          const classes: string[] = [];
          if (row.kind === 'theme') classes.push('wtr-theme-row');
          if (highlightedKey === row.key) classes.push('wtr-highlight-row');
          return classes.join(' ');
        }}
      />
      <style>{`
        .wtr-theme-row td {
          background: ${DARK_THEME.darkAccent} !important;
        }
        .wtr-highlight-row td {
          border-left: 3px solid ${DARK_THEME.cyanPrimary} !important;
          background: rgba(0,201,200,0.08) !important;
          transition: background 0.3s;
        }
      `}</style>
    </div>
  );
}
