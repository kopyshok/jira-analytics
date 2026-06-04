import { useState, useMemo, useEffect, useCallback, memo, type HTMLAttributes, type Key, type SyntheticEvent } from 'react';
import {
  Button, Space, Table, Tag, App,
  Select, Typography, Modal, Checkbox,
  Empty, Input,
} from 'antd';
import { CheckOutlined, CloseOutlined } from '@ant-design/icons';
import categoriesHelp from '../../../docs/help/categories.md?raw';
import { useRegisterHelp } from '../contexts/HelpContext';
import { useQueryClient } from '@tanstack/react-query';
import { Resizable } from 'react-resizable';
import 'react-resizable/css/styles.css';
import { useJiraSettings } from '../hooks/useSettings';
import { useGlobalTeamFilter } from '../hooks/useGlobalTeamFilter';
import { useScopeProjects } from '../hooks/useScope';
import { formatDateOnly, daysSince } from '../utils/format';
import { statusTagColor } from '../utils/status';
import { DARK_THEME } from '../utils/constants';
import { useCategories } from '../hooks/useCategories';
import { useSetIssueInclude, useBatchSetCategory, useVerifyIssue } from '../hooks/useIssueTree';
import {
  useIssueRoots,
  useIssueTreeCounts,
  useLoadChildrenMutation,
} from '../hooks/useIssueLazyTree';
import { getIssueChildrenByTab } from '../api/issues';
import type { IssueTreeRootNode } from '../types/api';

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

type TreeNodeWithChildren = IssueTreeRootNode & {
  children?: TreeNodeWithChildren[];
  __depth?: number;
};

type InnerTab = 'stack' | 'active' | 'initiatives' | 'archive_target' | 'archive';
const QUEUE_ORDER: InnerTab[] = ['stack', 'active', 'initiatives', 'archive_target', 'archive'];
const QUEUE_META: Record<InnerTab, { title: string; hint: string; tone: string }> = {
  stack: { title: 'К разбору', hint: 'без решения', tone: 'attention' },
  active: { title: 'Активные', hint: 'попадают в анализ', tone: 'success' },
  initiatives: { title: 'Инициативы', hint: 'на потом', tone: 'warning' },
  archive_target: { title: 'Архив квартальных целей', hint: 'квартальные цели старых периодов', tone: 'archive' },
  archive: { title: 'Архив неактуальных задач', hint: 'старые и не актуальные задачи', tone: 'muted' },
};

function countUnverifiedBelow(node: TreeNodeWithChildren): number {
  let count = 0;
  for (const child of node.children ?? []) {
    if (!child.category_verified) count++;
    count += countUnverifiedBelow(child);
  }
  return count;
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
  derivedCategory: string | null;
  categoryOptions: { value: string; label: string }[];
  categoryLabels: Record<string, string>;
  onChange: (issueId: string, code: string | null) => void;
};

const CategoryCell = memo(function CategoryCell({
  issueId, isGroup, isContext,
  hasPending, pendingValue, assignedValue,
  derivedCategory,
  categoryOptions, categoryLabels, onChange,
}: CategoryCellProps) {
  if (isGroup) return null;
  if (isContext) return <Text type="secondary" style={{ fontSize: 11 }}>контекст</Text>;
  const value = hasPending ? pendingValue : assignedValue;
  const derivedCat = !value ? derivedCategory : null;
  const placeholderCode = derivedCat;
  const placeholderLabel = placeholderCode
    ? (categoryLabels[placeholderCode] || placeholderCode)
    : 'Не назначена';
  return (
    <div onClick={(e) => e.stopPropagation()}>
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
    </div>
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
    <span onClick={(e) => e.stopPropagation()}>
      <Checkbox
        checked={checked}
        disabled={isContext}
        onChange={(e) => onToggle(issueId, e.target.checked)}
      />
    </span>
  );
});

// Constant Table props — lifted out of render so every click doesn't
// hand AntD a fresh object reference.
const tableComponents = { header: { cell: ResizableTitle } };
const tableScroll = { x: 1360, y: 'calc(100vh - 420px)' };

export default function CategoriesEditorPage() {
  const { notification, message } = App.useApp();
  const qc = useQueryClient();
  const { queryParams: globalQueryParams } = useGlobalTeamFilter();
  const selectedTeams = useMemo(
    () => (globalQueryParams.teams ? globalQueryParams.teams.split(',').filter(Boolean) : []),
    [globalQueryParams.teams],
  );
  const [hiddenStatuses, setHiddenStatuses] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const normalizedSearch = searchQuery.trim().toLowerCase();

  const [widths, setWidths] = useState<Record<string, number>>({
    key: 130, summary: 380, status: 140, statusChanged: 150, goals: 110,
    category: 260, include: 80,
    verify: 160,
  });
  const [innerTab, setInnerTab] = useState<InnerTab>('stack');
  const [pendingCats, setPendingCats] = useState<Map<string, string | null>>(new Map());
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [bulkModalOpen, setBulkModalOpen] = useState(false);
  const [bulkCategory, setBulkCategory] = useState<string | undefined>();
  const verifyMut = useVerifyIssue();
  useRegisterHelp('Категоризация задач', categoriesHelp);

  const scopeProjects = useScopeProjects();
  const scopeKeys = (scopeProjects.data ?? []).map(p => p.jira_project_key).join(',');

  const rootsQuery = useIssueRoots({
    project_keys: scopeKeys || undefined,
    teams: selectedTeams.length > 0 ? selectedTeams.join(',') : undefined,
    tab: innerTab,
    search: normalizedSearch || undefined,
  });
  const countsQuery = useIssueTreeCounts({
    project_keys: scopeKeys || undefined,
    teams: selectedTeams.length > 0 ? selectedTeams.join(',') : undefined,
  });

  const jiraSettings = useJiraSettings();
  const jiraBaseUrl = jiraSettings.data?.base_url ?? '';
  const setIncludeMut = useSetIssueInclude();
  const batchCategoryMut = useBatchSetCategory();
  const { options: categoryOptions, labels: categoryLabels } = useCategories();

  // ─── Lazy expand state ────────────────────────────────────────

  const [loadedChildren, setLoadedChildren] = useState<Map<string, IssueTreeRootNode[]>>(new Map());
  const loadChildrenMut = useLoadChildrenMutation();

  // Reset loaded children and expanded keys on tab/scope/team/search change
  useEffect(() => {
    setLoadedChildren(new Map());
    setExpandedRowKeys([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [innerTab, selectedTeams.join(','), scopeKeys, normalizedSearch]);

  const onExpand = useCallback(async (expanded: boolean, record: TreeNodeWithChildren) => {
    if (!expanded) return;
    if (loadedChildren.has(record.id)) return;
    if (!record.has_children) return;
    const children = await loadChildrenMut.mutateAsync({
      parentId: record.id,
      tab: innerTab,
      teams: selectedTeams.length > 0 ? selectedTeams.join(',') : undefined,
      project_keys: scopeKeys || undefined,
      search: normalizedSearch || undefined,
    });
    setLoadedChildren(prev => {
      const next = new Map(prev);
      next.set(record.id, children);
      return next;
    });
  }, [loadedChildren, loadChildrenMut, innerTab, selectedTeams, scopeKeys, normalizedSearch]);

  // ─── displayData from roots + loadedChildren ─────────────────

  const passesHiddenStatuses = useCallback((n: IssueTreeRootNode): boolean =>
    !hiddenStatuses.includes(n.status) || n.is_context,
  [hiddenStatuses]);

  const displayData = useMemo<TreeNodeWithChildren[]>(() => {
    const makeStub = (parent: IssueTreeRootNode, depth: number): TreeNodeWithChildren => ({
      ...parent,
      id: `__loading__${parent.id}`,
      key: '',
      summary: 'Загрузка…',
      issue_type: 'group',
      is_context: false,
      is_container: false,
      has_children: false,
      descendant_count: 0,
      descendant_match_count: 0,
      __depth: depth,
    } as TreeNodeWithChildren);
    const attachChildren = (node: IssueTreeRootNode, depth: number): TreeNodeWithChildren => {
      const kids = loadedChildren.get(node.id);
      if (kids) {
        const real = kids.filter(passesHiddenStatuses).map(k => attachChildren(k, depth + 1));
        return {
          ...node,
          __depth: depth,
          children: real.length > 0 ? real : undefined,
        };
      }
      // Не загружено: если backend сказал has_children, подставляем stub —
      // AntD покажет стрелку раскрытия, onExpand подгрузит реальных детей.
      if (node.has_children) {
        return { ...node, __depth: depth, children: [makeStub(node, depth + 1)] };
      }
      return { ...node, __depth: depth };
    };
    return (rootsQuery.data ?? []).filter(passesHiddenStatuses).map(r => attachChildren(r, 0));
  }, [rootsQuery.data, loadedChildren, passesHiddenStatuses]);

  // ─── Unique statuses from loaded data ────────────────────────

  const uniqueStatuses = useMemo(() => {
    const s = new Set<string>();
    (rootsQuery.data ?? []).forEach(n => { if (n.status) s.add(n.status); });
    Array.from(loadedChildren.values()).flat().forEach(n => { if (n.status) s.add(n.status); });
    return Array.from(s).sort();
  }, [rootsQuery.data, loadedChildren]);

  // ─── Tab counters from server ─────────────────────────────────

  const counts = useMemo(
    () => countsQuery.data ?? { stack: 0, active: 0, initiatives: 0, archive_target: 0, archive: 0 },
    [countsQuery.data],
  );

  const queueItems = useMemo(() => QUEUE_ORDER.map(key => ({
    key,
    count: counts[key],
    ...QUEUE_META[key],
  })), [counts]);

  // ─── setPendingCategory: только этой строки ──────────────────
  // Каскад на потомков делает бэкенд при verify cascade=true:
  // /issues/{id}/verify с category_code применяет код к корню + всем
  // невериф потомкам (уже верифицированные не трогаются). PM выбирает
  // код в Select родителя → жмёт «Подтвердить +N» в той же строке.

  const setPendingCategory = useCallback((issueId: string, code: string | null) => {
    setPendingCats(prev => {
      const next = new Map(prev);
      next.set(issueId, code);
      return next;
    });
  }, []);

  // ─── Context rows set ─────────────────────────────────────────

  const contextIdSet = useMemo(() => {
    const out = new Set<string>();
    (rootsQuery.data ?? []).forEach(n => { if (n.is_context) out.add(n.id); });
    Array.from(loadedChildren.values()).flat().forEach(n => { if (n.is_context) out.add(n.id); });
    return out;
  }, [rootsQuery.data, loadedChildren]);

  const applicableSelectedIds = useMemo(
    () => selectedIds.filter(id => !contextIdSet.has(id)),
    [selectedIds, contextIdSet],
  );

  const applyBulkCategory = async () => {
    if (!bulkCategory || applicableSelectedIds.length === 0) return;
    try {
      const res = await batchCategoryMut.mutateAsync({
        issueIds: applicableSelectedIds,
        categoryCode: bulkCategory,
        verify: true,
      });
      qc.invalidateQueries({ queryKey: ['issues', 'tree'] });
      void refreshLoadedChildren();
      setPendingCats(prev => {
        if (prev.size === 0) return prev;
        const next = new Map(prev);
        applicableSelectedIds.forEach(id => next.delete(id));
        return next;
      });
      setBulkModalOpen(false);
      setBulkCategory(undefined);
      setSelectedIds([]);
      const archived = res.archived_ids.length;
      if (archived > 0) {
        notification.success({
          title: `Применено категорий: ${applicableSelectedIds.length}`,
          description: `В архив: ${archived}`,
        });
      } else {
        message.success(`Применено категорий: ${applicableSelectedIds.length}`);
      }
    } catch (e) {
      notification.error({ title: 'Ошибка применения категории', description: (e as Error).message });
    }
  };

  // ─── Refresh loaded children after mutations ────────────────
  // Server-side invalidation рефетчит только корни (useIssueRoots), а
  // дети в loadedChildren остаются устаревшими — строки не уходят с
  // вкладки «К разбору» пока пользователь не свернёт/раскроет родителя.
  const refreshLoadedChildren = useCallback(async () => {
    const parentIds = Array.from(loadedChildren.keys());
    if (parentIds.length === 0) return;
    const next = new Map<string, IssueTreeRootNode[]>();
    await Promise.all(parentIds.map(async (pid) => {
      try {
        const kids = await getIssueChildrenByTab(pid, innerTab, {
          teams: selectedTeams.length > 0 ? selectedTeams.join(',') : undefined,
          project_keys: scopeKeys || undefined,
          search: normalizedSearch || undefined,
        });
        next.set(pid, kids);
      } catch {
        const stale = loadedChildren.get(pid);
        if (stale) next.set(pid, stale);
      }
    }));
    setLoadedChildren(next);
  }, [loadedChildren, innerTab, selectedTeams, scopeKeys, normalizedSearch]);

  // ─── Mutations → invalidate tree ─────────────────────────────

  const toggleInclude = useCallback((issueId: string, hasChildren: boolean, checked: boolean) => {
    setIncludeMut.mutate(
      { issueId, include: checked, recursive: hasChildren },
      {
        onSuccess: () => qc.invalidateQueries({ queryKey: ['issues', 'tree'] }),
        onError: (err) => notification.error({ title: 'Ошибка', description: err.message }),
      },
    );
  }, [setIncludeMut, notification, qc]);

  const handleVerify = useCallback((
    issueId: string,
    cascade: boolean,
  ) => {
    const hasCategoryCode = pendingCats.has(issueId);
    const categoryCode = hasCategoryCode ? (pendingCats.get(issueId) ?? null) : null;
    verifyMut.mutate(
      { issueId, cascade, categoryCode, hasCategoryCode },
      {
        onSuccess: () => {
          qc.invalidateQueries({ queryKey: ['issues', 'tree'] });
          void refreshLoadedChildren();
          if (hasCategoryCode) {
            setPendingCats(prev => {
              if (!prev.has(issueId)) return prev;
              const next = new Map(prev);
              next.delete(issueId);
              return next;
            });
          }
        },
        onError: (err) => notification.error({ title: 'Ошибка верификации', description: (err as Error).message }),
      },
    );
  }, [pendingCats, verifyMut, notification, qc, refreshLoadedChildren]);

  const handleResize = useCallback((colKey: string) =>
    (_: SyntheticEvent, { size }: { size: { width: number; height: number } }) => {
      setWidths(w => ({ ...w, [colKey]: size.width }));
    },
  []);

  // ─── Expand/collapse ─────────────────────────────────────────

  const [expandedRowKeys, setExpandedRowKeys] = useState<readonly Key[]>([]);

  const tableExpandable = useMemo(
    () => ({
      expandedRowKeys,
      onExpandedRowsChange: setExpandedRowKeys,
      onExpand,
      expandRowByClick: true,
    }),
    [expandedRowKeys, onExpand],
  );

  const expandAll = useCallback(async () => {
    const SAFETY_LIMIT = 500;
    const newLoaded = new Map(loadedChildren);
    const expandIds = new Set<string>(expandedRowKeys.map(String));
    const visited = new Set<string>();
    const queue: IssueTreeRootNode[] = [...(rootsQuery.data ?? [])];
    let safety = 0;
    while (queue.length > 0 && safety < SAFETY_LIMIT) {
      safety++;
      const node = queue.shift()!;
      if (visited.has(node.id)) continue;
      visited.add(node.id);
      if (!node.has_children) continue;
      expandIds.add(node.id);
      let kids = newLoaded.get(node.id);
      if (!kids) {
        kids = await loadChildrenMut.mutateAsync({
          parentId: node.id,
          tab: innerTab,
          teams: selectedTeams.length > 0 ? selectedTeams.join(',') : undefined,
          project_keys: scopeKeys || undefined,
          search: normalizedSearch || undefined,
        });
        newLoaded.set(node.id, kids);
      }
      queue.push(...kids);
    }
    if (safety >= SAFETY_LIMIT) {
      message.warning(`Дерево слишком большое — раскрытие остановлено на ${SAFETY_LIMIT} узлах.`);
    }
    setLoadedChildren(newLoaded);
    setExpandedRowKeys(Array.from(expandIds));
  }, [rootsQuery.data, loadedChildren, expandedRowKeys, loadChildrenMut, innerTab, message, selectedTeams, scopeKeys, normalizedSearch]);

  const collapseAll = useCallback(() => {
    setExpandedRowKeys([]);
    setLoadedChildren(new Map());
  }, []);

  // ─── Columns ──────────────────────────────────────────────────

  const baseColumns = useMemo(() => {
    const base = [
      {
        title: 'Ключ',
        dataIndex: 'key',
        key: 'key',
        width: widths.key,
        render: (key: string, record: IssueTreeRootNode) => {
          if (record.issue_type === 'group' || !key) return null;
          if (!jiraBaseUrl) return <Text strong style={{ whiteSpace: 'nowrap' }}>{key}</Text>;
          return (
            <Typography.Link href={`${jiraBaseUrl}/browse/${key}`} target="_blank" rel="noreferrer" style={{ whiteSpace: 'nowrap' }}>
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
          const count = record.descendant_match_count ?? 0;
          return (
            <span>
              <Text>{s}</Text>
              {count > 0 && (
                <Tag
                  color="default"
                  style={{ marginLeft: 6, fontSize: 11 }}
                  title="Подчинённых задач на этой вкладке"
                >
                  {count}
                </Tag>
              )}
            </span>
          );
        },
      },
      {
        title: 'Категория',
        key: 'category',
        width: widths.category,
        className: 'category-column',
        render: (_: unknown, record: TreeNodeWithChildren) => (
          <CategoryCell
            issueId={record.id}
            isGroup={record.issue_type === 'group'}
            isContext={!!record.is_context}
            hasPending={pendingCats.has(record.id)}
            pendingValue={pendingCats.get(record.id) ?? undefined}
            assignedValue={record.assigned_category || undefined}
            derivedCategory={record.category}
            categoryOptions={categoryOptions}
            categoryLabels={categoryLabels}
            onChange={setPendingCategory}
          />
        ),
      },
      {
        title: 'Статус',
        dataIndex: 'status',
        key: 'status',
        width: widths.status,
        render: (v: string, record: IssueTreeRootNode) =>
          v ? <Tag color={statusTagColor(v, record.status_category)}>{v}</Tag> : null,
      },
      {
        title: 'Статус изменён',
        dataIndex: 'status_changed_at',
        key: 'statusChanged',
        width: widths.statusChanged,
        sorter: (a: IssueTreeRootNode, b: IssueTreeRootNode) => {
          const ta = a.status_changed_at ? new Date(a.status_changed_at).getTime() : 0;
          const tb = b.status_changed_at ? new Date(b.status_changed_at).getTime() : 0;
          return ta - tb;
        },
        render: (iso: string | null, record: IssueTreeRootNode) => {
          if (record.issue_type === 'group') return null;
          if (!iso) return <Text type="secondary">—</Text>;
          const days = daysSince(iso);
          let ageColor: string = DARK_THEME.textMuted;
          if (days !== null) {
            if (days >= 365) ageColor = '#ff7875';
            else if (days >= 180) ageColor = DARK_THEME.yellow;
          }
          return (
            <Space orientation="vertical" size={0} style={{ lineHeight: 1.1 }}>
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
        sorter: (a: IssueTreeRootNode, b: IssueTreeRootNode) => (a.goals ?? '').localeCompare(b.goals ?? ''),
        render: (v: string | null, record: IssueTreeRootNode) => {
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
    pendingCats, categoryOptions, categoryLabels,
    setPendingCategory, toggleInclude, handleResize,
  ]);

  const stackExtraColumns = useMemo(() => [
    {
      title: 'Действие',
      key: 'verify',
      width: widths.verify,
      onHeaderCell: () => ({ width: widths.verify, onResize: handleResize('verify') }),
      render: (_: unknown, record: TreeNodeWithChildren) => {
        if (record.issue_type === 'group' || record.is_context) return null;
        const hasChildren = (record.children?.length ?? 0) > 0;
        const unverifiedBelow = hasChildren ? countUnverifiedBelow(record) : 0;
        if (hasChildren) {
          return (
            <Button
              type="primary"
              size="small"
              loading={verifyMut.isPending}
              onClick={(e) => { e.stopPropagation(); handleVerify(record.id, true); }}
            >
              Подтвердить{unverifiedBelow > 0 ? ` +${unverifiedBelow}` : ''}
            </Button>
          );
        }
        return (
          <Button
            size="small"
            loading={verifyMut.isPending}
            onClick={(e) => { e.stopPropagation(); handleVerify(record.id, false); }}
          >
            Подтвердить
          </Button>
        );
      },
    },
  ], [widths.verify, verifyMut.isPending, handleVerify, handleResize]);

  const columns = innerTab === 'stack'
    ? [...baseColumns, ...stackExtraColumns]
    : baseColumns;

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
    const hit = normalizedSearch && (record.key || '').toLowerCase() === normalizedSearch
      ? ' tree-row-search-hit'
      : '';
    return `tree-row-depth-${depth}${hasKids ? ' tree-row-has-children' : ''}${ctx}${hit}`;
  }, [normalizedSearch]);

  const emptyText = (
    <Empty
      image={Empty.PRESENTED_IMAGE_SIMPLE}
      description={
        <Space orientation="vertical" size={4}>
          <Text strong>{innerTab === 'stack' ? 'Все задачи разобраны' : `В очереди «${QUEUE_META[innerTab].title}» пока пусто`}</Text>
          <Text type="secondary">
            {innerTab === 'stack'
              ? 'В этой очереди нет задач без решения. Проверьте активные задачи или обновите данные.'
              : 'Смените очередь или фильтр, чтобы продолжить разбор.'}
          </Text>
        </Space>
      }
    >
      {innerTab === 'stack' ? (
        <Button type="primary" onClick={() => setInnerTab('active')}>
          Перейти к активным
        </Button>
      ) : (
        <Button onClick={() => setInnerTab('stack')}>
          Перейти к разбору
        </Button>
      )}
    </Empty>
  );

  return (
    <Space orientation="vertical" className="category-triage-shell">
      <section className="category-triage-header">
        <Space orientation="vertical" size={4}>
          <Typography.Title level={2} style={{ margin: 0 }}>
            Разбор задач
          </Typography.Title>
          <Text type="secondary">
            Выберите задачи, назначьте категорию и сохраните черновик.
          </Text>
        </Space>
        <Tag color={counts.stack > 0 ? 'gold' : 'cyan'} className="category-triage-attention">
          {counts.stack} ждут разбора
        </Tag>
      </section>

      <div className="category-queue-summary" aria-label="Очереди разбора задач">
        {queueItems.map(item => (
          <button
            key={item.key}
            type="button"
            className={`category-queue-card category-queue-${item.tone}${innerTab === item.key ? ' is-active' : ''}`}
            onClick={() => setInnerTab(item.key)}
          >
            <span className="category-queue-count">{item.count}</span>
            <span className="category-queue-title">{item.title}</span>
            <span className="category-queue-hint">{item.hint}</span>
          </button>
        ))}
      </div>

      <div className="category-toolbar">
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
          <Button size="small" onClick={expandAll}>Развернуть всё</Button>
          <Button size="small" onClick={collapseAll}>Свернуть всё</Button>
          <Input.Search
            placeholder="Поиск по ключу или названию"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onSearch={(v) => setSearchQuery(v)}
            allowClear
            size="small"
            style={{ width: 260 }}
          />
        </Space>
        <Space wrap>
          {rootsQuery.isFetching && (
            <Button
              danger
              icon={<CloseOutlined />}
              onClick={() => qc.cancelQueries({ queryKey: ['issues', 'tree', 'roots'] })}
            >
              Отменить загрузку
            </Button>
          )}
          <Button
            icon={<CheckOutlined />}
            disabled={applicableSelectedIds.length === 0}
            onClick={() => setBulkModalOpen(true)}
          >
            Категория для отмеченных ({applicableSelectedIds.length})
          </Button>
        </Space>
      </div>
      <div className="category-table-wrap">
        <Table<TreeNodeWithChildren>
          className="category-issue-table"
          dataSource={displayData}
          columns={columns as never}
          components={tableComponents}
          rowKey="id"
          rowSelection={rowSelection}
          rowClassName={rowClassName}
          loading={rootsQuery.isFetching || loadChildrenMut.isPending}
          pagination={false}
          size="small"
          expandable={tableExpandable}
          scroll={tableScroll}
          locale={{ emptyText }}
        />
      </div>
      <Modal
        title={`Установить категорию для ${applicableSelectedIds.length} задач`}
        open={bulkModalOpen}
        onCancel={() => { setBulkModalOpen(false); setBulkCategory(undefined); }}
        onOk={applyBulkCategory}
        okText="Применить"
        cancelText="Отмена"
        confirmLoading={batchCategoryMut.isPending}
        okButtonProps={{ disabled: !bulkCategory }}
      >
        <Text type="secondary">
          Категория будет применена и сразу подтверждена.
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
