import { useState, useMemo, useEffect, useCallback, useRef, memo, type HTMLAttributes, type Key, type SyntheticEvent } from 'react';
import {
  Button, Space, Table, Tag, App,
  Select, Typography, Modal, Checkbox, Switch,
  Empty, Input,
} from 'antd';
import {
  CheckOutlined, CloseOutlined,
  SaveOutlined, ToolOutlined,
} from '@ant-design/icons';
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
import { useIssueTree, useSetIssueInclude, useBatchSetCategory, useVerifyIssue } from '../hooks/useIssueTree';
import type { IssueTreeNode } from '../types/api';
import BulkTriageDrawer from '../components/categories/BulkTriageDrawer';

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

function patchVerified(nodes: IssueTreeNode[], issueId: string, cascade: boolean): IssueTreeNode[] {
  return nodes.map(n => {
    if (n.id === issueId) {
      const markTree = (node: IssueTreeNode): IssueTreeNode => ({
        ...node,
        category_verified: true,
        children: cascade ? node.children.map(markTree) : node.children,
      });
      return markTree(n);
    }
    return { ...n, children: patchVerified(n.children, issueId, cascade) };
  });
}

function matchesTab(effective: string | null, verified: boolean, tab: InnerTab): boolean {
  if (!verified) return tab === 'stack';
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
const tableScroll = { x: 1360, y: 'calc(100vh - 420px)' };

export default function CategoriesEditorPage() {
  const { notification, message } = App.useApp();
  const qc = useQueryClient();
  const { queryParams: globalQueryParams } = useGlobalTeamFilter();
  const selectedTeams = useMemo(
    () => (globalQueryParams.teams ? globalQueryParams.teams.split(',').filter(Boolean) : []),
    [globalQueryParams.teams],
  );
  const [hiddenStatuses, setHiddenStatuses] = useState<string[]>(['Отменено']);
  const [searchQuery, setSearchQuery] = useState('');
  const normalizedSearch = searchQuery.trim().toLowerCase();

  const [widths, setWidths] = useState<Record<string, number>>({
    key: 130, summary: 380, status: 140, statusChanged: 150, goals: 110,
    category: 260, include: 80,
    requireChildVerification: 120, verify: 160,
  });
  const [innerTab, setInnerTab] = useState<InnerTab>('stack');
  const [pendingCats, setPendingCats] = useState<Map<string, string | null>>(new Map());
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [bulkModalOpen, setBulkModalOpen] = useState(false);
  const [bulkCategory, setBulkCategory] = useState<string | undefined>();
  const [bulkDrawerOpen, setBulkDrawerOpen] = useState(false);
  const [pendingVerifyFlags, setPendingVerifyFlags] = useState<Map<string, boolean>>(new Map());
  const verifyMut = useVerifyIssue();
  useRegisterHelp('Категоризация задач', categoriesHelp);

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
        const selfMatches = matchesTab(effectiveFor(n), n.category_verified ?? true, tab);
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

  // Epic candidates for cascade: issues with assigned_category and children
  const epicCandidates = useMemo(() => {
    const out: { id: string; key: string; summary: string; assigned_category: string }[] = [];
    const walk = (nodes: IssueTreeNode[]) => {
      for (const n of nodes) {
        if (n.assigned_category && (n.children?.length ?? 0) > 0) {
          out.push({
            id: n.id,
            key: n.key,
            summary: n.summary,
            assigned_category: n.assigned_category,
          });
        }
        if (n.children?.length) walk(n.children);
      }
    };
    walk(issueTree.data ?? []);
    return out;
  }, [issueTree.data]);

  const countTriage = (nodes: TreeNodeWithChildren[], tab: InnerTab): number => {
    let n = 0;
    const walk = (arr: TreeNodeWithChildren[]) => {
      arr.forEach(node => {
        if (node.issue_type !== 'group' && !node.is_context) {
          if (matchesTab(effectiveFor(node), node.category_verified ?? true, tab)) n++;
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

  // Поиск по ключу/названию — фильтрует уже построенное дерево вкладки,
  // не трогая счётчики карточек. Узел остаётся, если совпадает сам или
  // содержит совпавшего потомка.
  const displayData = useMemo(() => {
    if (!normalizedSearch) return tabData;
    const walk = (nodes: TreeNodeWithChildren[]): TreeNodeWithChildren[] => {
      const out: TreeNodeWithChildren[] = [];
      for (const n of nodes) {
        const kids = walk(n.children ?? []);
        const selfMatch =
          (n.key ?? '').toLowerCase().includes(normalizedSearch)
          || (n.summary ?? '').toLowerCase().includes(normalizedSearch);
        if (selfMatch || kids.length > 0) {
          out.push({ ...n, children: kids.length > 0 ? kids : undefined });
        }
      }
      return out;
    };
    return walk(tabData);
  }, [tabData, normalizedSearch]);

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
    // Мерджим в существующее состояние, а не заменяем — иначе setQueryData
    // (оптимистичный патч верификации) триггерит эффект и схлопывает дерево.
    setExpandedRowKeys(prev => Array.from(new Set([...prev, ...keys])));
    // tabData умышленно не в зависимостях: он пересобирается на каждом pendingCats-
    // клике, а сброс раскрытия нам нужен только на структурных изменениях.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [issueTree.data, innerTab, selectedTeams, hiddenStatuses]);
  const tableExpandable = useMemo(
    () => ({ expandedRowKeys, onExpandedRowsChange: setExpandedRowKeys, expandRowByClick: true }),
    [expandedRowKeys],
  );

  const expandAll = useCallback(() => {
    const ids: string[] = [];
    const walk = (nodes: TreeNodeWithChildren[]) => {
      nodes.forEach(n => {
        if (n.children?.length) { ids.push(n.id); walk(n.children); }
      });
    };
    walk(displayData);
    setExpandedRowKeys(ids);
  }, [displayData]);

  // При активном поиске автоматически раскрываем все ветви с совпадениями.
  useEffect(() => {
    if (!normalizedSearch) return;
    const ids: string[] = [];
    const walk = (nodes: TreeNodeWithChildren[]) => {
      nodes.forEach(n => {
        if (n.children?.length) { ids.push(n.id); walk(n.children); }
      });
    };
    walk(displayData);
    setExpandedRowKeys(prev => Array.from(new Set([...prev, ...ids])));
  }, [normalizedSearch, displayData]);

  const collapseAll = useCallback(() => setExpandedRowKeys([]), []);

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

  const queueItems = useMemo(() => {
    const counts: Record<InnerTab, number> = {
      stack: stackCount,
      active: activeCount,
      initiatives: initiativesCount,
      archive_target: archiveTargetCount,
      archive: archiveCount,
    };
    return QUEUE_ORDER.map(key => ({
      key,
      count: counts[key],
      ...QUEUE_META[key],
    }));
  }, [stackCount, activeCount, initiativesCount, archiveTargetCount, archiveCount]);

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
          notification.error({ title: 'Ошибка', description: err.message });
          issueTree.refetch();
        },
      },
    );
  }, [qc, treeQueryKey, setIncludeMut, notification, issueTree]);

  const handleVerify = useCallback((
    issueId: string,
    cascade: boolean,
  ) => {
    const requireChildVerification = pendingVerifyFlags.get(issueId) ?? false;
    // Optimistic: patch cache immediately so items fade out without refetch
    const previous = qc.getQueryData<IssueTreeNode[]>(treeQueryKey);
    qc.setQueryData<IssueTreeNode[]>(treeQueryKey, old =>
      old ? patchVerified(old, issueId, cascade) : old,
    );
    verifyMut.mutate(
      { issueId, cascade, requireChildVerification },
      {
        onError: (err) => {
          // Rollback on failure
          qc.setQueryData(treeQueryKey, previous);
          notification.error({ title: 'Ошибка верификации', description: (err as Error).message });
        },
      },
    );
  }, [pendingVerifyFlags, verifyMut, notification, qc, treeQueryKey]);

  const handleResize = useCallback((colKey: string) =>
    (_: SyntheticEvent, { size }: { size: { width: number; height: number } }) => {
      setWidths(w => ({ ...w, [colKey]: size.width }));
    },
  []);

  // Индекс id → node. Нужен для cascade-эффекта setPendingCategory: чтобы от
  // родителя пройти его поддерево в текущем дереве. Пересоздаётся только при
  // изменении серверного дерева.
  const nodeById = useMemo(() => {
    const map = new Map<string, IssueTreeNode>();
    const walk = (nodes: IssueTreeNode[]) => {
      for (const n of nodes) {
        map.set(n.id, n);
        if (n.children?.length) walk(n.children);
      }
    };
    walk(issueTree.data ?? []);
    return map;
  }, [issueTree.data]);

  // Какие id поставлены каскадом (не вручную). Нужно чтобы смена кода на
  // родителе протащила обновление по уже каскадно-проставленным потомкам, но
  // не тронула ручной выбор PM, даже если он совпадает с прежним кодом
  // родителя. Сбрасывается там же где pendingCats.
  const cascadedIdsRef = useRef<Set<string>>(new Set());

  // Поставить категорию + (на вкладке «К разбору») каскадно её же — на
  // видимых потомков «в стеке». Граница каскада: потомок с явным ручным
  // выбором PM (своя assigned_category на сервере или ручной pending в этой
  // сессии). Каскадно-проставленные потомки продолжают подхватывать смену
  // кода родителя. При снятии (code=null) каскадно убираем pending у тех,
  // кому каскад его поставил.
  const setPendingCategory = useCallback((issueId: string, code: string | null) => {
    setPendingCats(prev => {
      const next = new Map(prev);
      next.set(issueId, code);
      cascadedIdsRef.current.delete(issueId); // ручной выбор PM на корне

      if (innerTab !== 'stack') return next;

      const root = nodeById.get(issueId);
      if (!root) return next;

      const cascaded = cascadedIdsRef.current;
      const visit = (children: IssueTreeNode[] | undefined) => {
        if (!children) return;
        for (const ch of children) {
          if (ch.issue_type === 'group') {
            visit(ch.children);
            continue;
          }
          if (ch.is_context) continue;

          const hasOwnAssigned = !!ch.assigned_category;
          if (hasOwnAssigned) continue; // ручной выбор на сервере = граница

          const hasPending = next.has(ch.id);
          const isCascaded = cascaded.has(ch.id);
          // Ручной pending PM (не каскадом) — не трогаем + не идём глубже.
          if (hasPending && !isCascaded) continue;

          if (code === null) {
            // Снятие у родителя — убираем каскадно-проставленного потомка.
            if (hasPending && isCascaded) {
              next.delete(ch.id);
              cascaded.delete(ch.id);
            }
          } else {
            next.set(ch.id, code);
            cascaded.add(ch.id);
          }
          visit(ch.children);
        }
      };
      visit(root.children);
      return next;
    });
  }, [innerTab, nodeById]);

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
      cascadedIdsRef.current = new Set();
      const parts: string[] = [];
      if (archivedIds.size > 0) parts.push(`в архив: ${archivedIds.size}`);
      if (skippedContainers.size > 0) parts.push(`пропущено родителей: ${skippedContainers.size}`);
      if (parts.length > 0) {
        notification.success({
          title: `Сохранено категорий: ${total}`,
          description: parts.join(' · '),
        });
      } else {
        message.success(`Сохранено категорий: ${total}`);
      }
    } catch (e) {
      notification.error({ title: 'Ошибка сохранения', description: (e as Error).message });
    }
  };

  // Memoised columns — stable across selectedIds changes, rebuilds only
  // when the inputs actually affecting cell output change. This is the
  // main fix for checkbox-click latency on large trees.
  const baseColumns = useMemo(() => {
    const base = [
      {
        title: 'Ключ',
        dataIndex: 'key',
        key: 'key',
        width: widths.key,
        render: (key: string, record: IssueTreeNode) => {
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
            inheritedAssigned={record.__inheritedAssigned}
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

  const stackExtraColumns = useMemo(() => [
    {
      title: 'Верифиц. детей',
      key: 'requireChildVerification',
      width: widths.requireChildVerification,
      onHeaderCell: () => ({ width: widths.requireChildVerification, onResize: handleResize('requireChildVerification') }),
      render: (_: unknown, record: TreeNodeWithChildren) => {
        if (record.issue_type === 'group' || record.is_context) return null;
        const hasChildren = (record.children?.length ?? 0) > 0;
        if (!hasChildren) return <span style={{ color: '#595959' }}>—</span>;
        const checked = pendingVerifyFlags.get(record.id) ?? record.require_child_verification ?? false;
        return (
          <Switch
            size="small"
            checked={checked}
            onChange={(val) => {
              setPendingVerifyFlags(prev => {
                const next = new Map(prev);
                next.set(record.id, val);
                return next;
              });
            }}
          />
        );
      },
    },
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
              onClick={() => handleVerify(record.id, true)}
            >
              Подтвердить{unverifiedBelow > 0 ? ` +${unverifiedBelow}` : ''}
            </Button>
          );
        }
        return (
          <Button
            size="small"
            loading={verifyMut.isPending}
            onClick={() => handleVerify(record.id, false)}
          >
            Подтвердить
          </Button>
        );
      },
    },
  ], [widths.requireChildVerification, widths.verify, pendingVerifyFlags, verifyMut.isPending, handleVerify, handleResize]);

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
    return `tree-row-depth-${depth}${hasKids ? ' tree-row-has-children' : ''}${ctx}`;
  }, []);

  const hasPending = pendingCats.size > 0;
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
        <Tag color={stackCount > 0 ? 'gold' : 'cyan'} className="category-triage-attention">
          {stackCount} ждут разбора
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
            icon={<ToolOutlined />}
            onClick={() => setBulkDrawerOpen(true)}
          >
            Массовые операции
          </Button>
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
          loading={issueTree.isFetching}
          pagination={false}
          size="small"
          expandable={tableExpandable}
          scroll={tableScroll}
          locale={{ emptyText }}
        />
      </div>
      {hasPending && (
        <div className="category-draft-bar" role="status">
          <Space orientation="vertical" size={0}>
            <Text strong>{pendingCats.size} изменений в черновике</Text>
            <Text type="secondary">Можно продолжить разбор или сохранить изменения сейчас.</Text>
          </Space>
          <Space wrap>
            <Button
              icon={<CloseOutlined />}
              onClick={() => { setPendingCats(new Map()); cascadedIdsRef.current = new Set(); }}
            >
              Отменить
            </Button>
            <Button
              type="primary"
              icon={<SaveOutlined />}
              loading={batchCategoryMut.isPending}
              onClick={savePending}
            >
              Сохранить изменения
            </Button>
          </Space>
        </div>
      )}
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
      <BulkTriageDrawer
        open={bulkDrawerOpen}
        onClose={() => setBulkDrawerOpen(false)}
        selectedTeams={selectedTeams}
        scopeProjectKeys={(scopeProjects.data ?? []).map(p => p.jira_project_key)}
        epicCandidates={epicCandidates}
      />
    </Space>
  );
}
