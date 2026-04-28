import { useState, useMemo, useEffect, useRef, useCallback, memo, type HTMLAttributes, type Key, type SyntheticEvent } from 'react';
import {
  Button, Card, Space, Table, Tag, App,
  Tabs, Select, Typography, Modal, Checkbox, Popconfirm, DatePicker, Progress,
} from 'antd';
import {
  SyncOutlined, ReloadOutlined,
  CheckOutlined, CloseOutlined,
  SaveOutlined, ExclamationCircleOutlined,
} from '@ant-design/icons';
import { useQueryClient } from '@tanstack/react-query';
import { Resizable } from 'react-resizable';
import 'react-resizable/css/styles.css';
import dayjs, { type Dayjs } from 'dayjs';
import { useJiraSettings, useSaveGenericSetting, useGenericSetting } from '../hooks/useSettings';
import {
  useSyncStatus, useSyncMutation, useRecalculateMapping,
  useReloadWorklogs, useUpdateWorklogs,
} from '../hooks/useSync';
import { useGlobalTeamFilter } from '../hooks/useGlobalTeamFilter';
import {
  useScopeProjects,
} from '../hooks/useScope';
import { formatDate, formatDateOnly, daysSince } from '../utils/format';
import { statusTagColor } from '../utils/status';
import { DARK_THEME } from '../utils/constants';
import { useCategories } from '../hooks/useCategories';
import { useIssueTree, useSetIssueInclude, useBatchSetCategory } from '../hooks/useIssueTree';
import PageHeader from '../components/shared/PageHeader';
import type { IssueTreeNode } from '../types/api';
import type {
  SyncStatusResponse,
} from '../types/api';
import type { WorklogReloadProgress, WorklogUpdateProgress } from '../api/sync';

const { Text } = Typography;

// ─── Category config tab (tree) ─────────────────────────────────

type ResizableTitleProps = HTMLAttributes<HTMLTableCellElement> & {
  width?: number;
  onResize?: (e: SyntheticEvent, data: { size: { width: number; height: number } }) => void;
};

function ResizableTitle({ onResize, width, ...rest }: ResizableTitleProps) {
  if (!width) return <th {...rest} />;
  return (
    <Resizable
      width={width}
      height={0}
      handle={
        <span
          className="react-resizable-handle"
          onClick={(e) => e.stopPropagation()}
        />
      }
      onResize={onResize}
      draggableOpts={{ enableUserSelectHack: false }}
    >
      <th {...rest} />
    </Resizable>
  );
}

type TreeNodeWithChildren = Omit<IssueTreeNode, 'children'> & {
  children?: TreeNodeWithChildren[];
  __depth?: number;
  // Ближайший assigned_category предка (уже с учётом pending). Дети наследуют
  // категорию эпика визуально, иначе PRJ-9882 (archive) остаётся в «стеке»,
  // потому что его 24 ребёнка без собственной категории якорят его.
  __inheritedAssigned?: string | null;
};

type InnerTab = 'stack' | 'active' | 'initiatives' | 'archive_target' | 'archive';
const ARCHIVE_CODES = new Set(['archive', 'archive_target']);
const INITIATIVES_CODE = 'initiatives_rfa';

function matchesTab(effective: string | null, tab: InnerTab): boolean {
  switch (tab) {
    case 'stack': return effective === null;
    case 'active':
      return (
        effective !== null
        && !ARCHIVE_CODES.has(effective)
        && effective !== INITIATIVES_CODE
      );
    case 'initiatives': return effective === INITIATIVES_CODE;
    case 'archive_target': return effective === 'archive_target';
    case 'archive': return effective === 'archive';
  }
}

// ─── Memoised table cells ────────────────────────────────────────
// Cell rerenders are driven by primitive per-row props, not the whole
// record — so selecting a checkbox (which only flips rowSelection)
// never re-enters these components.

type CategoryCellProps = {
  issueId: string;
  isGroup: boolean;
  isContext: boolean;
  hasPending: boolean;
  pendingValue: string | undefined;
  assignedValue: string | undefined;
  inheritedAssigned: string | null | undefined;
  derivedCategory: string | null;
  categoryOptions: { value: string; label: string }[];
  categoryLabels: Record<string, string>;
  onChange: (issueId: string, code: string | null) => void;
};

const CategoryCell = memo(function CategoryCell({
  issueId, isGroup, isContext,
  hasPending, pendingValue, assignedValue,
  inheritedAssigned, derivedCategory,
  categoryOptions, categoryLabels, onChange,
}: CategoryCellProps) {
  if (isGroup) return null;
  if (isContext) return <Text type="secondary" style={{ fontSize: 11 }}>контекст</Text>;
  const value = hasPending ? pendingValue : assignedValue;
  const ancestorCat = !value ? inheritedAssigned ?? null : null;
  const derivedCat = !value && !ancestorCat ? derivedCategory : null;
  const placeholderCode = ancestorCat ?? derivedCat;
  const placeholderLabel = placeholderCode
    ? (ancestorCat ? '↑ ' : '') + (categoryLabels[placeholderCode] || placeholderCode)
    : 'Не назначена';
  return (
    <Select
      placeholder={placeholderLabel}
      value={value}
      onChange={(val) => onChange(issueId, val || null)}
      allowClear
      size="small"
      style={{
        width: '100%',
        opacity: !value && placeholderCode ? 0.6 : 1,
        boxShadow: hasPending ? `0 0 4px ${DARK_THEME.cyanPrimary}` : undefined,
      }}
      options={categoryOptions}
    />
  );
});

type IncludeCellProps = {
  issueId: string;
  isGroup: boolean;
  isContext: boolean;
  checked: boolean;
  onToggle: (issueId: string, checked: boolean) => void;
};

const IncludeCell = memo(function IncludeCell({
  issueId, isGroup, isContext, checked, onToggle,
}: IncludeCellProps) {
  if (isGroup) return null;
  return (
    <Checkbox
      checked={checked}
      disabled={isContext}
      onChange={(e) => onToggle(issueId, e.target.checked)}
    />
  );
});

// Constant Table props — lifted out of render so every click doesn't
// hand AntD a fresh object reference.
const tableComponents = { header: { cell: ResizableTitle } };
const tableScroll = { y: 'calc(100vh - 320px)' };

export function CategoryConfigTab() {
  const { notification, message } = App.useApp();
  const qc = useQueryClient();
  const { queryParams: globalQueryParams } = useGlobalTeamFilter();
  const selectedTeams = useMemo(
    () => (globalQueryParams.teams ? globalQueryParams.teams.split(',').filter(Boolean) : []),
    [globalQueryParams.teams],
  );
  const [hiddenStatuses, setHiddenStatuses] = useState<string[]>(['Отменено']);

  const [widths, setWidths] = useState<Record<string, number>>({
    key: 110, summary: 380, status: 140, statusChanged: 150, goals: 110, category: 260, include: 80,
  });
  const [innerTab, setInnerTab] = useState<InnerTab>('stack');
  const [pendingCats, setPendingCats] = useState<Map<string, string | null>>(new Map());
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [bulkModalOpen, setBulkModalOpen] = useState(false);
  const [bulkCategory, setBulkCategory] = useState<string | undefined>();

  const scopeProjects = useScopeProjects();
  const scopeKeys = (scopeProjects.data ?? []).map(p => p.jira_project_key).join(',');
  const issueTreeParams = useMemo(
    () => ({
      project_keys: scopeKeys || undefined,
      teams: selectedTeams.length > 0 ? selectedTeams.join(',') : undefined,
    }),
    [scopeKeys, selectedTeams],
  );
  const issueTree = useIssueTree(issueTreeParams);
  const jiraSettings = useJiraSettings();
  const jiraBaseUrl = jiraSettings.data?.base_url ?? '';
  const setIncludeMut = useSetIssueInclude();
  const batchCategoryMut = useBatchSetCategory();
  const { options: categoryOptions, labels: categoryLabels } = useCategories();

  const treeQueryKey = useMemo(() => ['issues', 'tree', issueTreeParams], [issueTreeParams]);

  // Effective assigned category (server + pending)
  const effectiveAssigned = (node: IssueTreeNode): string | null | undefined => {
    if (pendingCats.has(node.id)) return pendingCats.get(node.id);
    return node.assigned_category ?? null;
  };

  // Unique statuses from loaded data (for status filter dropdown)
  const uniqueStatuses = useMemo(() => {
    const s = new Set<string>();
    const walk = (nodes: IssueTreeNode[]) => {
      nodes.forEach(n => { if (n.status) s.add(n.status); walk(n.children); });
    };
    walk(issueTree.data ?? []);
    return Array.from(s).sort();
  }, [issueTree.data]);

  // Effective category for a node = own (pending/assigned) OR nearest ancestor's
  // assigned_category. Used to route nodes into the right tab.
  const effectiveFor = (n: TreeNodeWithChildren): string | null => {
    const own = effectiveAssigned(n as IssueTreeNode);
    if (own) return own;
    return n.__inheritedAssigned ?? null;
  };

  // Builds the tree for a given tab: node is kept if it self-matches the tab
  // OR any of its descendants does. Annotates __depth + __inheritedAssigned.
  const buildTabData = (tab: InnerTab): TreeNodeWithChildren[] => {
    const walk = (
      nodes: IssueTreeNode[],
      depth: number,
      parentAssigned: string | null,
    ): TreeNodeWithChildren[] => nodes
      .map(n => {
        const own = effectiveAssigned(n) ?? null;
        const passDown = own ?? parentAssigned;
        const kids = walk(n.children, depth + 1, passDown);
        return {
          ...n,
          __depth: depth,
          __inheritedAssigned: parentAssigned,
          children: kids.length > 0 ? kids : undefined,
        };
      })
      .filter(n => {
        if (n.issue_type === 'group') return (n.children?.length ?? 0) > 0;
        if (hiddenStatuses.includes(n.status) && !(n.children?.length ?? 0)) return false;
        if (n.is_context) return (n.children?.length ?? 0) > 0;
        const selfMatches = matchesTab(effectiveFor(n), tab);
        return selfMatches || (n.children?.length ?? 0) > 0;
      });
    return walk(issueTree.data ?? [], 0, null);
  };

  // Count of all descendant tasks in the raw loaded tree — not filtered by
  // tab / hidden status / category. Virtual group nodes don't count as
  // tasks. Recomputed only when the server-side tree changes, not on
  // pendingCats flips.
  const descendantCounts = useMemo(() => {
    const map = new Map<string, number>();
    const dfs = (node: IssueTreeNode): number => {
      let count = 0;
      for (const child of node.children) {
        const childSubtree = dfs(child);
        if (child.issue_type !== 'group') count += 1;
        count += childSubtree;
      }
      map.set(node.id, count);
      return count;
    };
    (issueTree.data ?? []).forEach(dfs);
    return map;
  }, [issueTree.data]);

  const countTriage = (nodes: TreeNodeWithChildren[], tab: InnerTab): number => {
    let n = 0;
    const walk = (arr: TreeNodeWithChildren[]) => {
      arr.forEach(node => {
        if (node.issue_type !== 'group' && !node.is_context) {
          if (matchesTab(effectiveFor(node), tab)) n++;
        }
        if (node.children) walk(node.children);
      });
    };
    walk(nodes);
    return n;
  };

  const stackData = useMemo(
    () => buildTabData('stack'),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [issueTree.data, hiddenStatuses, pendingCats],
  );
  const activeData = useMemo(
    () => buildTabData('active'),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [issueTree.data, hiddenStatuses, pendingCats],
  );
  const initiativesData = useMemo(
    () => buildTabData('initiatives'),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [issueTree.data, hiddenStatuses, pendingCats],
  );
  const archiveTargetData = useMemo(
    () => buildTabData('archive_target'),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [issueTree.data, hiddenStatuses, pendingCats],
  );
  const archiveData = useMemo(
    () => buildTabData('archive'),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [issueTree.data, hiddenStatuses, pendingCats],
  );

  const tabData =
    innerTab === 'stack' ? stackData
    : innerTab === 'active' ? activeData
    : innerTab === 'initiatives' ? initiativesData
    : innerTab === 'archive_target' ? archiveTargetData
    : archiveData;

  // Контекстные строки (родители вне фильтра команды) при загрузке автоматически
  // раскрываем вместе со всей цепочкой предков — пользователю нужно сразу видеть
  // реальную задачу внутри фильтра. Пользователь может свернуть вручную; сброс
  // только при смене вкладки / фильтра команды / перезагрузке дерева — правки
  // pendingCats expansion не трогают.
  const [expandedRowKeys, setExpandedRowKeys] = useState<readonly Key[]>([]);
  useEffect(() => {
    const keys = new Set<string>();
    const walk = (nodes: TreeNodeWithChildren[], ancestors: string[]) => {
      nodes.forEach(n => {
        if (n.is_context) {
          keys.add(n.id);
          ancestors.forEach(a => keys.add(a));
        }
        if (n.children?.length) walk(n.children, [...ancestors, n.id]);
      });
    };
    walk(tabData, []);
    setExpandedRowKeys(Array.from(keys));
    // tabData умышленно не в зависимостях: он пересобирается на каждом pendingCats-
    // клике, а сброс раскрытия нам нужен только на структурных изменениях.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [issueTree.data, innerTab, selectedTeams, hiddenStatuses]);
  const tableExpandable = useMemo(
    () => ({ expandedRowKeys, onExpandedRowsChange: setExpandedRowKeys }),
    [expandedRowKeys],
  );

  // Counts walk the whole tree — memoise per tab so selectedIds changes
  // don't re-trigger four tree walks. countTriage closes over pendingCats
  // (via effectiveFor/effectiveAssigned), so we match the buildTabData
  // deps pattern: whenever pendingCats changes, tabData is rebuilt too.
  const stackCount = useMemo(() => countTriage(stackData, 'stack'),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [stackData]);
  const activeCount = useMemo(() => countTriage(activeData, 'active'),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [activeData]);
  const initiativesCount = useMemo(() => countTriage(initiativesData, 'initiatives'),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [initiativesData]);
  const archiveTargetCount = useMemo(() => countTriage(archiveTargetData, 'archive_target'),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [archiveTargetData]);
  const archiveCount = useMemo(() => countTriage(archiveData, 'archive'),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [archiveData]);

  const tabItems = useMemo(() => [
    { key: 'stack', label: `Стек задач к разбору (${stackCount})` },
    { key: 'active', label: `Активный стек (${activeCount})` },
    { key: 'initiatives', label: `Бэклог инициатив (${initiativesCount})` },
    { key: 'archive_target', label: `Архив квартальных задач (${archiveTargetCount})` },
    { key: 'archive', label: `Архив прочих задач (${archiveCount})` },
  ], [stackCount, activeCount, initiativesCount, archiveTargetCount, archiveCount]);

  // Optimistic toggle for include_in_analysis.
  // Takes (issueId, hasChildren) instead of full record so memoized cells
  // can pass only primitives and benefit from React.memo equality.
  const toggleInclude = useCallback((issueId: string, hasChildren: boolean, checked: boolean) => {
    const patchSubtree = (node: IssueTreeNode): IssueTreeNode => ({
      ...node,
      include_in_analysis: checked,
      children: node.children.map(patchSubtree),
    });
    const patchTree = (nodes: IssueTreeNode[]): IssueTreeNode[] => nodes.map(n => {
      if (n.id === issueId) {
        return hasChildren ? patchSubtree(n) : { ...n, include_in_analysis: checked };
      }
      return { ...n, children: patchTree(n.children) };
    });
    qc.setQueryData<IssueTreeNode[]>(treeQueryKey, (old) => old ? patchTree(old) : old);
    setIncludeMut.mutate(
      { issueId, include: checked, recursive: hasChildren },
      {
        onError: (err) => {
          notification.error({ message: 'Ошибка', description: err.message });
          issueTree.refetch();
        },
      },
    );
  }, [qc, treeQueryKey, setIncludeMut, notification, issueTree]);

  const handleResize = useCallback((colKey: string) =>
    (_: SyntheticEvent, { size }: { size: { width: number; height: number } }) => {
      setWidths(w => ({ ...w, [colKey]: size.width }));
    },
  []);

  const setPendingCategory = useCallback((issueId: string, code: string | null) => {
    setPendingCats(prev => {
      const next = new Map(prev);
      next.set(issueId, code);
      return next;
    });
  }, []);

  // Ids of context rows — ancestor rows outside the team filter, surfaced
  // only to keep hierarchy readable. The user can tick their checkbox as a
  // bulk-select gesture (cascade picks up descendants), but the context row
  // itself must never receive a category.
  const contextIdSet = useMemo(() => {
    const out = new Set<string>();
    const walk = (nodes: IssueTreeNode[]) => {
      nodes.forEach(n => {
        if (n.is_context) out.add(n.id);
        walk(n.children);
      });
    };
    walk(issueTree.data ?? []);
    return out;
  }, [issueTree.data]);

  const applicableSelectedIds = useMemo(
    () => selectedIds.filter(id => !contextIdSet.has(id)),
    [selectedIds, contextIdSet],
  );

  const applyBulkCategory = () => {
    if (!bulkCategory || applicableSelectedIds.length === 0) return;
    setPendingCats(prev => {
      const next = new Map(prev);
      applicableSelectedIds.forEach(id => next.set(id, bulkCategory));
      return next;
    });
    setBulkModalOpen(false);
    setBulkCategory(undefined);
    setSelectedIds([]);
  };

  const savePending = async () => {
    // Group by category code
    const groups = new Map<string | null, string[]>();
    pendingCats.forEach((code, id) => {
      const arr = groups.get(code) ?? [];
      arr.push(id);
      groups.set(code, arr);
    });
    try {
      const archivedIds = new Set<string>();
      const skippedContainers = new Set<string>();
      const assignments = new Map<string, string | null>();
      for (const [code, ids] of groups) {
        const res = await batchCategoryMut.mutateAsync({ issueIds: ids, categoryCode: code });
        const skippedForGroup = new Set(res.skipped_containers ?? []);
        skippedForGroup.forEach(id => skippedContainers.add(id));
        ids.forEach(id => {
          if (!skippedForGroup.has(id)) assignments.set(id, code);
        });
        res.archived_ids.forEach(id => archivedIds.add(id));
      }
      // Patch the local tree cache so UI reflects saved state without a refetch.
      const patchTree = (nodes: IssueTreeNode[]): IssueTreeNode[] => nodes.map(n => {
        const nextAssigned = assignments.has(n.id) ? assignments.get(n.id) ?? null : n.assigned_category;
        const nextInclude = archivedIds.has(n.id) ? false : n.include_in_analysis;
        return {
          ...n,
          assigned_category: nextAssigned,
          include_in_analysis: nextInclude,
          children: patchTree(n.children),
        };
      });
      qc.setQueryData<IssueTreeNode[]>(treeQueryKey, (old) => old ? patchTree(old) : old);

      const total = assignments.size;
      setPendingCats(new Map());
      const parts: string[] = [];
      if (archivedIds.size > 0) parts.push(`в архив: ${archivedIds.size}`);
      if (skippedContainers.size > 0) parts.push(`пропущено родителей: ${skippedContainers.size}`);
      if (parts.length > 0) {
        notification.success({
          message: `Сохранено категорий: ${total}`,
          description: parts.join(' · '),
        });
      } else {
        message.success(`Сохранено категорий: ${total}`);
      }
    } catch (e) {
      notification.error({ message: 'Ошибка сохранения', description: (e as Error).message });
    }
  };

  // Memoised columns — stable across selectedIds changes, rebuilds only
  // when the inputs actually affecting cell output change. This is the
  // main fix for checkbox-click latency on large trees.
  const columns = useMemo(() => {
    const base = [
      {
        title: 'Ключ',
        dataIndex: 'key',
        key: 'key',
        width: widths.key,
        render: (key: string, record: IssueTreeNode) => {
          if (record.issue_type === 'group' || !key) return null;
          if (!jiraBaseUrl) return <Text strong>{key}</Text>;
          return (
            <Typography.Link href={`${jiraBaseUrl}/browse/${key}`} target="_blank" rel="noreferrer">
              {key}
            </Typography.Link>
          );
        },
      },
      {
        title: 'Название',
        dataIndex: 'summary',
        key: 'summary',
        width: widths.summary,
        render: (s: string, record: TreeNodeWithChildren) => {
          const count = descendantCounts.get(record.id) ?? 0;
          return (
            <span>
              <Text>{s}</Text>
              {count > 0 && (
                <Tag
                  color="default"
                  style={{ marginLeft: 6, fontSize: 11 }}
                  title="Всего подчинённых задач в иерархии (без фильтров)"
                >
                  {count}
                </Tag>
              )}
            </span>
          );
        },
      },
      {
        title: 'Статус',
        dataIndex: 'status',
        key: 'status',
        width: widths.status,
        render: (v: string, record: IssueTreeNode) =>
          v ? <Tag color={statusTagColor(v, record.status_category)}>{v}</Tag> : null,
      },
      {
        title: 'Статус изменён',
        dataIndex: 'status_changed_at',
        key: 'statusChanged',
        width: widths.statusChanged,
        sorter: (a: IssueTreeNode, b: IssueTreeNode) => {
          const ta = a.status_changed_at ? new Date(a.status_changed_at).getTime() : 0;
          const tb = b.status_changed_at ? new Date(b.status_changed_at).getTime() : 0;
          return ta - tb;
        },
        render: (iso: string | null, record: IssueTreeNode) => {
          if (record.issue_type === 'group') return null;
          if (!iso) return <Text type="secondary">—</Text>;
          const days = daysSince(iso);
          let ageColor: string = DARK_THEME.textMuted;
          if (days !== null) {
            if (days >= 365) ageColor = '#ff7875';
            else if (days >= 180) ageColor = DARK_THEME.yellow;
          }
          return (
            <Space direction="vertical" size={0} style={{ lineHeight: 1.1 }}>
              <Text style={{ fontSize: 12 }}>{formatDateOnly(iso)}</Text>
              {days !== null && (
                <Text style={{ fontSize: 11, color: ageColor }}>{days} д назад</Text>
              )}
            </Space>
          );
        },
      },
      {
        title: 'Цели',
        dataIndex: 'goals',
        key: 'goals',
        width: widths.goals,
        sorter: (a: IssueTreeNode, b: IssueTreeNode) => (a.goals ?? '').localeCompare(b.goals ?? ''),
        render: (v: string | null, record: IssueTreeNode) => {
          if (record.issue_type === 'group') return null;
          if (!v) return <Text type="secondary">—</Text>;
          return (
            <Space size={4} wrap>
              {v.split(',').map(s => s.trim()).filter(Boolean).map(tag => (
                <Tag key={tag} color="purple">{tag}</Tag>
              ))}
            </Space>
          );
        },
      },
      {
        title: 'Категория',
        key: 'category',
        width: widths.category,
        render: (_: unknown, record: TreeNodeWithChildren) => (
          <CategoryCell
            issueId={record.id}
            isGroup={record.issue_type === 'group'}
            isContext={!!record.is_context}
            hasPending={pendingCats.has(record.id)}
            pendingValue={pendingCats.get(record.id) ?? undefined}
            assignedValue={record.assigned_category || undefined}
            inheritedAssigned={record.__inheritedAssigned}
            derivedCategory={record.category}
            categoryOptions={categoryOptions}
            categoryLabels={categoryLabels}
            onChange={setPendingCategory}
          />
        ),
      },
      {
        title: 'В анализ',
        key: 'include',
        width: widths.include,
        render: (_: unknown, record: TreeNodeWithChildren) => (
          <IncludeCell
            issueId={record.id}
            isGroup={record.issue_type === 'group'}
            isContext={!!record.is_context}
            checked={record.include_in_analysis}
            onToggle={(id, checked) =>
              toggleInclude(id, (record.children?.length ?? 0) > 0, checked)
            }
          />
        ),
      },
    ];
    return base.map(col => ({
      ...col,
      onHeaderCell: () => ({ width: col.width, onResize: handleResize(col.key) }),
    }));
  }, [
    widths, jiraBaseUrl,
    pendingCats, categoryOptions, categoryLabels, descendantCounts,
    setPendingCategory, toggleInclude, handleResize,
  ]);

  // rowSelection is stable across everything but selectedIds changes, so
  // AntD updates only the checkbox column internally.
  // Context rows are selectable (as a cascade handle for their subtree),
  // but the apply step filters them out so they don't pick up a category.
  const rowSelection = useMemo(() => ({
    selectedRowKeys: selectedIds,
    onChange: (keys: React.Key[]) => setSelectedIds(keys.map(String)),
    checkStrictly: false,
    getCheckboxProps: (record: TreeNodeWithChildren) => ({
      disabled: record.issue_type === 'group',
    }),
  }), [selectedIds]);

  const rowClassName = useCallback((record: TreeNodeWithChildren) => {
    const depth = Math.min(record.__depth ?? 0, 5);
    const hasKids = (record.children?.length ?? 0) > 0;
    const ctx = record.is_context ? ' tree-row-context' : '';
    return `tree-row-depth-${depth}${hasKids ? ' tree-row-has-children' : ''}${ctx}`;
  }, []);

  const hasPending = pendingCats.size > 0;

  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      <Space wrap>
        <Select
          mode="multiple"
          placeholder="Скрытые статусы"
          value={hiddenStatuses}
          onChange={setHiddenStatuses}
          allowClear
          style={{ minWidth: 280 }}
          options={uniqueStatuses.map(s => ({ value: s, label: s }))}
          maxTagCount="responsive"
        />
        {issueTree.isFetching && (
          <Button
            danger
            icon={<CloseOutlined />}
            onClick={() => qc.cancelQueries({ queryKey: treeQueryKey })}
          >
            Отменить загрузку
          </Button>
        )}
        <Button
          icon={<CheckOutlined />}
          disabled={applicableSelectedIds.length === 0}
          onClick={() => setBulkModalOpen(true)}
        >
          Установить категорию отмеченным ({applicableSelectedIds.length})
        </Button>
        {hasPending && (
          <>
            <Tag color="blue">Изменений: {pendingCats.size}</Tag>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              loading={batchCategoryMut.isPending}
              onClick={savePending}
            >
              Сохранить
            </Button>
            <Button
              icon={<CloseOutlined />}
              onClick={() => setPendingCats(new Map())}
            >
              Отмена
            </Button>
          </>
        )}
      </Space>
      <Tabs
        activeKey={innerTab}
        onChange={(k) => setInnerTab(k as InnerTab)}
        items={tabItems}
      />
      <Table<TreeNodeWithChildren>
        dataSource={tabData}
        columns={columns as never}
        components={tableComponents}
        rowKey="id"
        rowSelection={rowSelection}
        rowClassName={rowClassName}
        loading={issueTree.isFetching}
        pagination={false}
        size="small"
        expandable={tableExpandable}
        scroll={tableScroll}
      />
      <Modal
        title={`Установить категорию для ${applicableSelectedIds.length} задач`}
        open={bulkModalOpen}
        onCancel={() => { setBulkModalOpen(false); setBulkCategory(undefined); }}
        onOk={applyBulkCategory}
        okText="Применить"
        cancelText="Отмена"
        okButtonProps={{ disabled: !bulkCategory }}
      >
        <Text type="secondary">
          Категория будет отмечена как «к сохранению». Для применения нажмите «Сохранить».
          {selectedIds.length > applicableSelectedIds.length && (
            <>
              <br />
              Контекстные строки (родители вне фильтра команды) пропускаются — отмечено
              {' '}{selectedIds.length - applicableSelectedIds.length}, категорию получат {applicableSelectedIds.length}.
            </>
          )}
        </Text>
        <div style={{ marginTop: 12 }}>
          <Select
            placeholder="Выберите категорию"
            value={bulkCategory}
            onChange={setBulkCategory}
            showSearch
            optionFilterProp="label"
            style={{ width: '100%' }}
            options={categoryOptions}
          />
        </div>
      </Modal>
    </Space>
  );
}

// ─── Sync controls ───────────────────────────────────────────────

function SyncControls() {
  const { notification } = App.useApp();
  const { data: statuses, isLoading } = useSyncStatus();
  const recalculate = useRecalculateMapping();
  const scopeProjects = useScopeProjects();
  const scopeKeys = (scopeProjects.data ?? []).map(p => p.jira_project_key);

  const fullSyncMut = useSyncMutation('full');
  const incrementalSyncMut = useSyncMutation('full');
  const worklogsMut = useSyncMutation('worklogs');
  const commentsMut = useSyncMutation('comments');

  // AbortControllers для прерываемых sync-запросов. При клике на
  // «Прервать» вызываем abort() → fetch бросает AbortError → бэкенд
  // видит is_disconnected и поднимает CancelledError → 499.
  const fullAbortRef = useRef<AbortController | null>(null);
  const incAbortRef = useRef<AbortController | null>(null);
  const wlAbortRef = useRef<AbortController | null>(null);
  const reloadAbortRef = useRef<AbortController | null>(null);

  const reloadSince = useGenericSetting('worklog_reload_since_date');
  const saveReloadSince = useSaveGenericSetting();
  const reload = useReloadWorklogs();
  const storedSinceDate = useMemo(
    () => dayjs(reloadSince.data?.value || '2026-01-01'),
    [reloadSince.data?.value],
  );
  const [selectedSinceDate, setSelectedSinceDate] = useState<Dayjs | null>(null);
  const sinceDate = selectedSinceDate ?? storedSinceDate;
  const [reloadProgress, setReloadProgress] = useState<WorklogReloadProgress | null>(null);

  const handleReload = () => {
    const iso = sinceDate.format('YYYY-MM-DD');
    const ctl = new AbortController();
    reloadAbortRef.current = ctl;
    setReloadProgress(null);
    reload.mutate({
      req: { since: iso },
      onProgress: (e) => setReloadProgress(e),
      signal: ctl.signal,
    }, {
      onSuccess: (stats) => {
        notification.success({
          message: "Worklog'и перезагружены",
          description: `Удалено: ${stats.deleted}, issues: ${stats.issues_scanned}, вставлено: ${stats.worklogs_inserted}`,
        });
        saveReloadSince.mutate({ key: 'worklog_reload_since_date', value: iso });
      },
      onError: (e) => {
        if (e.name === 'AbortError') return;
        notification.error({ message: 'Ошибка', description: e.message });
      },
      onSettled: () => {
        reloadAbortRef.current = null;
        setReloadProgress(null);
      },
    });
  };

  const handleFullSync = () => {
    const body = { project_keys: scopeKeys.length > 0 ? scopeKeys : undefined, incremental: false };
    const ctl = new AbortController();
    fullAbortRef.current = ctl;
    fullSyncMut.mutate({ body, signal: ctl.signal }, {
      onSuccess: (res) => notification.success({ message: 'Полная синхронизация', description: res.message }),
      onError: (e) => {
        if (e.name === 'AbortError') return;
        notification.error({ message: 'Ошибка синхронизации', description: e.message });
      },
      onSettled: () => { fullAbortRef.current = null; },
    });
  };

  const handleIncrementalSync = () => {
    const body = { project_keys: scopeKeys.length > 0 ? scopeKeys : undefined, incremental: true };
    const ctl = new AbortController();
    incAbortRef.current = ctl;
    incrementalSyncMut.mutate({ body, signal: ctl.signal }, {
      onSuccess: (res) => notification.success({ message: 'Обновление', description: res.message }),
      onError: (e) => {
        if (e.name === 'AbortError') return;
        notification.error({ message: 'Ошибка обновления', description: e.message });
      },
      onSettled: () => { incAbortRef.current = null; },
    });
  };

  const handleWorklogs = () => {
    const ctl = new AbortController();
    wlAbortRef.current = ctl;
    worklogsMut.mutate({ signal: ctl.signal }, {
      onSuccess: () => {
        // Комментарии идут под тем же контроллером — один «Прервать»
        // отменяет всю связку ворклоги→комменты.
        commentsMut.mutate({ signal: ctl.signal }, {
          onSuccess: (res) => notification.success({ message: 'Ворклоги и комментарии', description: res.message }),
          onError: (e) => {
            if (e.name === 'AbortError') return;
            notification.error({ message: 'Ошибка комментариев', description: e.message });
          },
          onSettled: () => { wlAbortRef.current = null; },
        });
      },
      onError: (e) => {
        wlAbortRef.current = null;
        if (e.name === 'AbortError') return;
        notification.error({ message: 'Ошибка ворклогов', description: e.message });
      },
    });
  };

  const cancelFullSync = () => fullAbortRef.current?.abort();
  const cancelIncSync = () => incAbortRef.current?.abort();
  const cancelWorklogs = () => wlAbortRef.current?.abort();
  const cancelReload = () => reloadAbortRef.current?.abort();

  const update = useUpdateWorklogs();
  const updateAbortRef = useRef<AbortController | null>(null);
  const [updateProgress, setUpdateProgress] = useState<WorklogUpdateProgress | null>(null);
  const [includeTeams, setIncludeTeams] = useState<boolean>(false);
  const storedCategoryTeams = useGenericSetting('ui_teams_categories');
  const selectedTeams = useMemo(
    () => (storedCategoryTeams.data?.value ?? '').split(',').filter(Boolean),
    [storedCategoryTeams.data],
  );

  const handleUpdate = () => {
    const iso = sinceDate.format('YYYY-MM-DD');
    const ctl = new AbortController();
    updateAbortRef.current = ctl;
    setUpdateProgress(null);
    update.mutate({
      req: {
        since: iso,
        teams: includeTeams && selectedTeams.length ? selectedTeams : undefined,
      },
      onProgress: (e) => setUpdateProgress(e),
      signal: ctl.signal,
    }, {
      onSuccess: (stats) => {
        notification.success({
          message: 'Ворклоги обновлены',
          description:
            `A: issues ${stats.bucket_a_issues_scanned}, worklog ${stats.bucket_a_worklogs_upserted}. ` +
            `B: issues ${stats.bucket_b_issues_scanned}, worklog ${stats.bucket_b_worklogs_upserted}, ` +
            `новых вне scope ${stats.bucket_b_out_of_scope_created}`,
        });
        saveReloadSince.mutate({ key: 'worklog_reload_since_date', value: iso });
      },
      onError: (e) => {
        if (e.name === 'AbortError') return;
        notification.error({ message: 'Ошибка обновления', description: e.message });
      },
      onSettled: () => {
        updateAbortRef.current = null;
        setUpdateProgress(null);
      },
    });
  };

  const cancelUpdate = () => updateAbortRef.current?.abort();

  const statusColumns = [
    {
      title: 'Сущность',
      key: 'entity',
      render: (_: unknown, record: SyncStatusResponse) =>
        record.scope
          ? <>{record.entity} <Tag color="geekblue">{record.scope}</Tag></>
          : record.entity,
    },
    {
      title: 'Последняя синхронизация',
      dataIndex: 'last_sync',
      key: 'last_sync',
      render: (v: string | null) => formatDate(v),
    },
    {
      title: 'Ошибка',
      dataIndex: 'last_error',
      key: 'last_error',
      render: (v: string | null) => v ? <Tag color="red">{v}</Tag> : <Tag color="green">OK</Tag>,
    },
  ];

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Card title="Синхронизация" size="small">
        <Space direction="vertical" style={{ width: '100%' }}>
          <Space wrap>
            {incrementalSyncMut.isPending ? (
              <Button danger icon={<CloseOutlined />} onClick={cancelIncSync}>
                Прервать обновление
              </Button>
            ) : (
              <Button
                type="primary"
                icon={<SyncOutlined />}
                onClick={handleIncrementalSync}
              >
                Обновить
              </Button>
            )}
            {fullSyncMut.isPending ? (
              <Button danger icon={<CloseOutlined />} onClick={cancelFullSync}>
                Прервать полную синхронизацию
              </Button>
            ) : (
              <Popconfirm
                title="Полная синхронизация"
                description={
                  <div style={{ maxWidth: 320 }}>
                    Перечитает все задачи из Jira заново (десятки минут, ~115k+ тасков).
                    В повседневке используйте «Обновить» — она тянет только изменившееся.
                  </div>
                }
                icon={<ExclamationCircleOutlined style={{ color: '#faad14' }} />}
                okText="Запустить"
                cancelText="Отмена"
                okButtonProps={{ danger: true }}
                onConfirm={handleFullSync}
              >
                <Button icon={<SyncOutlined />}>
                  Полная синхронизация
                </Button>
              </Popconfirm>
            )}
            {(worklogsMut.isPending || commentsMut.isPending) ? (
              <Button danger icon={<CloseOutlined />} onClick={cancelWorklogs}>
                Прервать ворклоги
              </Button>
            ) : (
              <Button icon={<SyncOutlined />} onClick={handleWorklogs}>
                Ворклоги
              </Button>
            )}
          </Space>
          <Space wrap>
            <DatePicker
              value={sinceDate}
              onChange={(d) => d && setSelectedSinceDate(d)}
              format="DD.MM.YYYY"
              allowClear={false}
              disabled={reload.isPending || update.isPending}
            />
            {update.isPending ? (
              <Button danger icon={<CloseOutlined />} onClick={cancelUpdate}>
                Прервать обновление
              </Button>
            ) : (
              <Button
                type="primary"
                icon={<ReloadOutlined />}
                onClick={handleUpdate}
                disabled={reload.isPending}
              >
                Обновить ворклоги с даты
              </Button>
            )}
            <Checkbox
              checked={includeTeams}
              disabled={update.isPending || selectedTeams.length === 0}
              onChange={(e) => setIncludeTeams(e.target.checked)}
            >
              Включить выбранные команды ({selectedTeams.length})
            </Checkbox>
            {reload.isPending ? (
              <Button danger icon={<CloseOutlined />} onClick={cancelReload}>
                Прервать полную перезагрузку
              </Button>
            ) : (
              <Popconfirm
                title="Полная перезагрузка ворклогов"
                description={
                  <div style={{ maxWidth: 340 }}>
                    <b>Удалит</b> все worklog с started ≥ {sinceDate.format('DD.MM.YYYY')} и перечитает
                    из Jira. Используется только если в Jira удалили ворклог и нужно подчистить локальную
                    копию. В повседневке — «Обновить ворклоги с даты».
                  </div>
                }
                icon={<ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />}
                okText="Перезагрузить"
                cancelText="Отмена"
                okButtonProps={{ danger: true }}
                onConfirm={handleReload}
                disabled={update.isPending}
              >
                <Button danger icon={<ReloadOutlined />} disabled={update.isPending}>
                  Полная перезагрузка (удалить и перечитать)
                </Button>
              </Popconfirm>
            )}
          </Space>
          {(reload.isPending || update.isPending) && (
            <Space direction="vertical" size={2} style={{ width: '100%', maxWidth: 640 }}>
              <Progress
                percent={99.9}
                status="active"
                showInfo={false}
                strokeColor={DARK_THEME.cyanPrimary}
              />
              <Text type="secondary" style={{ fontSize: 12 }}>
                {update.isPending ? (
                  updateProgress
                    ? `A: issues ${updateProgress.bucket_a_issues_scanned} · worklog ${updateProgress.bucket_a_worklogs_upserted} · B: issues ${updateProgress.bucket_b_issues_scanned} · worklog ${updateProgress.bucket_b_worklogs_upserted} · новых ${updateProgress.bucket_b_out_of_scope_created}${updateProgress.current_key ? ` · ${updateProgress.current_key}` : ''}`
                    : 'Подготовка…'
                ) : (
                  reloadProgress
                    ? `Удалено: ${reloadProgress.deleted} · Обработано ${reloadProgress.issues_scanned} · Вставлено ${reloadProgress.worklogs_inserted}${reloadProgress.current_key ? ` · ${reloadProgress.current_key}` : ''}`
                    : 'Подготовка…'
                )}
              </Text>
            </Space>
          )}
          {scopeKeys.length > 0 && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              Scope: {scopeKeys.join(', ')}
            </Text>
          )}
        </Space>
      </Card>

      <Card
        title="Статус"
        size="small"
        extra={
          <Button
            icon={<ReloadOutlined />}
            onClick={() => recalculate.mutate(undefined, {
              onSuccess: (res) => notification.success({ message: 'Маппинг', description: res.message }),
              onError: (e) => notification.error({ message: 'Ошибка маппинга', description: e.message }),
            })}
            loading={recalculate.isPending}
            size="small"
          >
            Пересчитать маппинг
          </Button>
        }
      >
        <Table<SyncStatusResponse>
          dataSource={statuses}
          columns={statusColumns}
          rowKey={(r) => `${r.entity}::${r.scope}`}
          loading={isLoading}
          pagination={false}
          size="small"
        />
      </Card>
    </Space>
  );
}

// ─── Main page ───────────────────────────────────────────────────

export default function SyncPage() {
  return (
    <>
      <PageHeader
        eyebrow="Данные"
        title="Задачи · Синхронизация"
        subtitle="Категоризация задач в древовидной структуре и управление синхронизацией с Jira"
      />
      <Tabs
        items={[
          { key: 'categories', label: 'Категоризация задач', children: <CategoryConfigTab /> },
          { key: 'sync', label: 'Синхронизация', children: <SyncControls /> },
        ]}
      />
    </>
  );
}
