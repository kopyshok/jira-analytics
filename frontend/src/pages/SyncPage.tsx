import { useState, useMemo, useEffect, type HTMLAttributes, type SyntheticEvent } from 'react';
import {
  Button, Card, Space, Table, Tag, App, Input, Switch,
  Tabs, Select, Typography, Modal, Checkbox, Popconfirm,
} from 'antd';
import {
  SyncOutlined, ApiOutlined, ReloadOutlined, SearchOutlined,
  CheckOutlined, CloseOutlined,
  SaveOutlined, SettingOutlined, ExclamationCircleOutlined,
} from '@ant-design/icons';
import { useQueryClient } from '@tanstack/react-query';
import { Resizable } from 'react-resizable';
import 'react-resizable/css/styles.css';
import { testConnection, getJiraProjects } from '../api/sync';
import { useJiraSettings, useSaveJiraSettings, useTestJiraCredentials, useSaveGenericSetting, useGenericSetting } from '../hooks/useSettings';
import {
  useSyncStatus, useSyncMutation, useRecalculateMapping,
  useJiraProjects, useBatchScopeProjects,
  useJiraTeams, useJiraFields, useRefreshIssuesByKeys,
} from '../hooks/useSync';
import {
  useScopeProjects, useRemoveScopeProject,
} from '../hooks/useScope';
import { formatDate, formatDateOnly, daysSince } from '../utils/format';
import { DARK_THEME } from '../utils/constants';
import { useCategories } from '../hooks/useCategories';
import { useIssueTree, useSetIssueInclude, useBatchSetCategory } from '../hooks/useIssueTree';
import type { IssueTreeNode } from '../types/api';
import type {
  SyncStatusResponse,
  JiraProjectItem,
} from '../types/api';

const { Text } = Typography;

// ─── Connection card ─────────────────────────────────────────────

function ConnectionCard() {
  const { message } = App.useApp();
  const settings = useJiraSettings();
  const saveMutation = useSaveJiraSettings();
  const testMutation = useTestJiraCredentials();

  const [email, setEmail] = useState('');
  const [token, setToken] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [loaded, setLoaded] = useState(false);

  // Populate form from saved settings once
  if (settings.data && !loaded) {
    if (settings.data.email) setEmail(settings.data.email);
    if (settings.data.base_url) setBaseUrl(settings.data.base_url);
    setLoaded(true);
  }

  const handleSave = () => {
    const body: Record<string, string> = {};
    if (email) body.email = email;
    if (token) body.api_token = token;
    if (baseUrl) body.base_url = baseUrl;
    saveMutation.mutate(body, {
      onSuccess: () => message.success('Настройки сохранены'),
      onError: (e) => message.error(e.message),
    });
  };

  const handleTest = () => {
    const testEmail = email || settings.data?.email || '';
    const testUrl = baseUrl || settings.data?.base_url || '';
    if (!testEmail || !testUrl) {
      message.warning('Укажите Email и Base URL');
      return;
    }
    if (!token && !settings.data?.has_token) {
      message.warning('Укажите API Token');
      return;
    }
    // If no new token, test via old endpoint (credentials are already in DB)
    if (!token && settings.data?.has_token) {
      testConnection().then((res) => {
        if (res.connected) message.success(`Подключение успешно (${res.user_name})`);
        else message.error(res.error || 'Не удалось подключиться');
      }).catch((e: Error) => message.error(e.message));
      return;
    }
    testMutation.mutate(
      { email: testEmail, api_token: token, base_url: testUrl },
      {
        onSuccess: (res) => {
          if (res.connected) message.success(`Подключение успешно (${res.user_name})`);
          else message.error(res.error || 'Не удалось подключиться');
        },
        onError: (e) => message.error(e.message),
      },
    );
  };

  return (
    <Card title="Подключение к Jira" size="small">
      <Space direction="vertical" style={{ width: '100%' }}>
        <Space wrap>
          <Input
            placeholder="Base URL (https://your-domain.atlassian.net)"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            style={{ width: 360 }}
          />
          <Input
            placeholder="Email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={{ width: 260 }}
          />
          <Input.Password
            placeholder={settings.data?.has_token ? 'Токен сохранён (введите новый для замены)' : 'API Token'}
            value={token}
            onChange={(e) => setToken(e.target.value)}
            style={{ width: 300 }}
          />
        </Space>
        <Space>
          <Button
            icon={<SaveOutlined />}
            type="primary"
            onClick={handleSave}
            loading={saveMutation.isPending}
          >
            Сохранить
          </Button>
          <Button
            icon={<ApiOutlined />}
            onClick={handleTest}
            loading={testMutation.isPending}
          >
            Проверить подключение
          </Button>
          {testMutation.data?.connected && (
            <Text type="success">
              {testMutation.data.user_name} ({testMutation.data.user_email})
            </Text>
          )}
        </Space>
      </Space>
    </Card>
  );
}

// ─── Project browser with scope toggle ───────────────────────────

function TaskSectionsTab() {
  const { notification, message } = App.useApp();
  const qc = useQueryClient();
  const [search, setSearch] = useState('');
  const [selectedTeam, setSelectedTeam] = useState<string | undefined>();
  const [teamHydrated, setTeamHydrated] = useState(false);
  const [loadingAll, setLoadingAll] = useState(false);
  const jiraProjects = useJiraProjects(search, selectedTeam);
  const scopeProjects = useScopeProjects();
  const batchMutation = useBatchScopeProjects();
  const jiraTeams = useJiraTeams();
  const jiraFields = useJiraFields();
  const saveFieldSetting = useSaveGenericSetting();
  const saveUiSetting = useSaveGenericSetting();
  const storedTeam = useGenericSetting('ui_team_projects');
  const productField = useGenericSetting('jira_team_field_id');
  const participatingField = useGenericSetting('jira_participating_teams_field_id');
  const [showFieldModal, setShowFieldModal] = useState(false);
  const [productFieldDraft, setProductFieldDraft] = useState<string | undefined>();
  const [participatingFieldDraft, setParticipatingFieldDraft] = useState<string | undefined>();

  // Hydrate team selection from AppSetting once on first load; subsequent
  // changes are persisted immediately.
  useEffect(() => {
    if (teamHydrated || storedTeam.data === undefined) return;
    const val = storedTeam.data?.value;
    if (val) setSelectedTeam(val);
    setTeamHydrated(true);
  }, [teamHydrated, storedTeam.data]);

  const handleTeamChange = (val: string | undefined) => {
    setSelectedTeam(val);
    saveUiSetting.mutate({ key: 'ui_team_projects', value: val ?? '' });
  };

  // Track pending changes before save
  const [pendingAdd, setPendingAdd] = useState<Set<string>>(new Set());
  const [pendingRemove, setPendingRemove] = useState<Set<string>>(new Set());

  const hasPending = pendingAdd.size > 0 || pendingRemove.size > 0;

  const scopeKeys = useMemo(
    () => new Set((scopeProjects.data ?? []).map(p => p.jira_project_key)),
    [scopeProjects.data],
  );

  const dataSource = useMemo(() => {
    if (!jiraProjects.data) return [];
    return jiraProjects.data.map(p => {
      let inScope = scopeKeys.has(p.key);
      if (pendingAdd.has(p.key)) inScope = true;
      if (pendingRemove.has(p.key)) inScope = false;
      return { ...p, in_scope: inScope };
    });
  }, [jiraProjects.data, scopeKeys, pendingAdd, pendingRemove]);

  const toggleScope = (key: string, currentlyInScope: boolean) => {
    if (currentlyInScope) {
      // wants to remove
      if (pendingAdd.has(key)) {
        setPendingAdd(prev => { const n = new Set(prev); n.delete(key); return n; });
      } else {
        setPendingRemove(prev => new Set(prev).add(key));
      }
    } else {
      // wants to add
      if (pendingRemove.has(key)) {
        setPendingRemove(prev => { const n = new Set(prev); n.delete(key); return n; });
      } else {
        setPendingAdd(prev => new Set(prev).add(key));
      }
    }
  };

  const handleSave = () => {
    batchMutation.mutate(
      { add: [...pendingAdd], remove: [...pendingRemove] },
      {
        onSuccess: (res) => {
          notification.success({ message: 'Scope обновлён', description: `Добавлено: ${res.added}, удалено: ${res.removed}` });
          setPendingAdd(new Set());
          setPendingRemove(new Set());
        },
        onError: (e) => notification.error({ message: 'Ошибка', description: e.message }),
      },
    );
  };

  const columns = [
    {
      title: 'В scope',
      dataIndex: 'in_scope',
      key: 'in_scope',
      width: 80,
      render: (inScope: boolean, record: JiraProjectItem) => {
        const isPending = pendingAdd.has(record.key) || pendingRemove.has(record.key);
        return (
          <Switch
            checked={inScope}
            onChange={() => toggleScope(record.key, inScope)}
            size="small"
            style={isPending ? { boxShadow: `0 0 4px ${DARK_THEME.cyanPrimary}` } : undefined}
          />
        );
      },
    },
    { title: 'Ключ', dataIndex: 'key', key: 'key', width: 120 },
    { title: 'Название', dataIndex: 'name', key: 'name' },
    { title: 'Тип', dataIndex: 'project_type', key: 'project_type', width: 120 },
  ];

  const openFieldModal = () => {
    jiraFields.refetch();
    setProductFieldDraft(productField.data?.value ?? undefined);
    setParticipatingFieldDraft(participatingField.data?.value ?? undefined);
    setShowFieldModal(true);
  };

  const handleLoadAll = async () => {
    handleTeamChange(undefined);
    setSearch('');
    setLoadingAll(true);
    try {
      const data = await getJiraProjects(undefined, undefined);
      qc.setQueryData(['jira', 'projects', '', undefined], data);
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setLoadingAll(false);
    }
  };

  const handleSaveFields = async () => {
    try {
      await saveFieldSetting.mutateAsync({
        key: 'jira_team_field_id',
        value: productFieldDraft ?? '',
      });
      await saveFieldSetting.mutateAsync({
        key: 'jira_participating_teams_field_id',
        value: participatingFieldDraft ?? '',
      });
      message.success('Поля команды сохранены');
      setShowFieldModal(false);
      jiraTeams.refetch();
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  return (
    <Card
      title="Разделы задач"
      size="small"
      extra={
        <Space>
          <Button
            icon={<SettingOutlined />}
            size="small"
            onClick={openFieldModal}
          >
            Настройка полей команды
          </Button>
          {hasPending && (
            <>
              <Tag color="blue">Изменений: {pendingAdd.size + pendingRemove.size}</Tag>
              <Button
                type="primary"
                size="small"
                icon={<CheckOutlined />}
                loading={batchMutation.isPending}
                onClick={handleSave}
              >
                Сохранить
              </Button>
              <Button
                size="small"
                icon={<CloseOutlined />}
                onClick={() => { setPendingAdd(new Set()); setPendingRemove(new Set()); }}
              >
                Отмена
              </Button>
            </>
          )}
        </Space>
      }
    >
      <Space direction="vertical" style={{ width: '100%' }}>
        <Space wrap>
          <Select
            placeholder="Команда (продуктовая или участвующая)"
            value={selectedTeam}
            onChange={handleTeamChange}
            allowClear
            style={{ width: 320 }}
            options={(jiraTeams.data ?? []).map(t => ({ value: t, label: t }))}
            onDropdownVisibleChange={(open) => { if (open && !jiraTeams.data) jiraTeams.refetch(); }}
            loading={jiraTeams.isFetching}
            notFoundContent={jiraTeams.isError ? 'Настройте поля команды' : undefined}
          />
          <Input
            placeholder="Поиск по ключу или названию"
            prefix={<SearchOutlined />}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ width: 300 }}
            allowClear
          />
          <Button
            icon={<SyncOutlined spin={jiraProjects.isFetching && !loadingAll} />}
            onClick={() => jiraProjects.refetch()}
            loading={jiraProjects.isFetching && !loadingAll}
          >
            Загрузить из Jira
          </Button>
          <Button
            icon={<SyncOutlined spin={loadingAll} />}
            onClick={handleLoadAll}
            loading={loadingAll}
          >
            Загрузить все ключи
          </Button>
        </Space>
        <Table<JiraProjectItem>
          dataSource={dataSource}
          columns={columns}
          rowKey="key"
          loading={jiraProjects.isFetching || loadingAll}
          pagination={{ defaultPageSize: 15, showSizeChanger: true, pageSizeOptions: ['15', '50', '100'] }}
          size="small"
        />
      </Space>

      <Modal
        title="Настройка полей команды"
        open={showFieldModal}
        onCancel={() => setShowFieldModal(false)}
        onOk={handleSaveFields}
        okText="Сохранить"
        cancelText="Отмена"
        confirmLoading={saveFieldSetting.isPending}
        width={640}
      >
        <Space direction="vertical" style={{ width: '100%' }} size="middle">
          <Text type="secondary">
            Фильтр команд в списке проектов объединяет оба поля через ИЛИ.
            Можно оставить только одно из полей — второе будет проигнорировано.
          </Text>
          <div>
            <Text strong>Продуктовая команда</Text>
            <Select
              placeholder="Выберите поле Jira"
              value={productFieldDraft}
              onChange={setProductFieldDraft}
              allowClear
              showSearch
              optionFilterProp="label"
              loading={jiraFields.isFetching}
              style={{ width: '100%', marginTop: 6 }}
              options={(jiraFields.data ?? [])
                .filter(f => f.custom)
                .map(f => ({ value: f.id, label: `${f.name} (${f.id})` }))}
            />
          </div>
          <div>
            <Text strong>Участвующие команды</Text>
            <Select
              placeholder="Выберите поле Jira"
              value={participatingFieldDraft}
              onChange={setParticipatingFieldDraft}
              allowClear
              showSearch
              optionFilterProp="label"
              loading={jiraFields.isFetching}
              style={{ width: '100%', marginTop: 6 }}
              options={(jiraFields.data ?? [])
                .filter(f => f.custom)
                .map(f => ({ value: f.id, label: `${f.name} (${f.id})` }))}
            />
          </div>
        </Space>
      </Modal>
    </Card>
  );
}

// ─── Current scope summary ───────────────────────────────────────

function ScopeOverview() {
  const { data } = useScopeProjects();
  const remove = useRemoveScopeProject();

  return (
    <Card title="Текущий scope" size="small">
      {(!data || data.length === 0) ? (
        <Text type="secondary">Scope пуст — при синхронизации будут загружены все проекты</Text>
      ) : (
        <Space wrap>
          {data.map(p => (
            <Tag
              key={p.id}
              closable
              onClose={(e) => { e.preventDefault(); remove.mutate(p.jira_project_key); }}
              color="blue"
            >
              {p.jira_project_key}
            </Tag>
          ))}
        </Space>
      )}
    </Card>
  );
}

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

function CategoryConfigTab() {
  const { notification, message } = App.useApp();
  const qc = useQueryClient();
  const [selectedTeams, setSelectedTeams] = useState<string[]>([]);
  const [teamsHydrated, setTeamsHydrated] = useState(false);
  const [hiddenStatuses, setHiddenStatuses] = useState<string[]>(['Отменено']);
  const storedTeams = useGenericSetting('ui_teams_categories');
  const saveUiSetting = useSaveGenericSetting();

  // Hydrate once from AppSetting; changes are persisted via handleTeamsChange.
  useEffect(() => {
    if (teamsHydrated || storedTeams.data === undefined) return;
    const val = storedTeams.data?.value;
    if (val) setSelectedTeams(val.split(',').filter(Boolean));
    setTeamsHydrated(true);
  }, [teamsHydrated, storedTeams.data]);

  const handleTeamsChange = (val: string[]) => {
    setSelectedTeams(val);
    saveUiSetting.mutate({ key: 'ui_teams_categories', value: val.join(',') });
  };

  const [widths, setWidths] = useState<Record<string, number>>({
    key: 110, summary: 380, status: 140, statusChanged: 150, category: 260, include: 80,
  });
  const [innerTab, setInnerTab] = useState<'stack' | 'sorted'>('stack');
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
  const jiraTeams = useJiraTeams();
  const jiraSettings = useJiraSettings();
  const jiraBaseUrl = jiraSettings.data?.base_url ?? '';
  const setIncludeMut = useSetIssueInclude();
  const batchCategoryMut = useBatchSetCategory();
  const refreshMut = useRefreshIssuesByKeys();
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

  // Filter: status + tab (stack = no effective category; sorted = has effective category).
  // Annotates __depth + __inheritedAssigned so rows can be tinted per level and
  // categorized descendants of a categorized parent fall out of the stack.
  const buildTabData = (wantSorted: boolean): TreeNodeWithChildren[] => {
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
        // Context ancestors never self-match — они лишь якори для детей.
        if (n.is_context) return (n.children?.length ?? 0) > 0;
        const own = !!effectiveAssigned(n as IssueTreeNode);
        const inherited = !!n.__inheritedAssigned;
        const hasCat = own || inherited;
        const selfMatches = wantSorted ? hasCat : !hasCat;
        return selfMatches || (n.children?.length ?? 0) > 0;
      });
    return walk(issueTree.data ?? [], 0, null);
  };

  const countTriage = (nodes: TreeNodeWithChildren[], wantSorted: boolean): number => {
    let n = 0;
    const walk = (arr: TreeNodeWithChildren[]) => {
      arr.forEach(node => {
        if (node.issue_type !== 'group' && !node.is_context) {
          const own = !!effectiveAssigned(node as IssueTreeNode);
          const inherited = !!node.__inheritedAssigned;
          const hasCat = own || inherited;
          if (wantSorted ? hasCat : !hasCat) n++;
        }
        if (node.children) walk(node.children);
      });
    };
    walk(nodes);
    return n;
  };

  const stackData = useMemo(
    () => buildTabData(false),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [issueTree.data, hiddenStatuses, pendingCats],
  );
  const sortedData = useMemo(
    () => buildTabData(true),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [issueTree.data, hiddenStatuses, pendingCats],
  );

  const tabData = innerTab === 'stack' ? stackData : sortedData;

  // Optimistic toggle for include_in_analysis
  const toggleInclude = (record: IssueTreeNode, checked: boolean) => {
    const recursive = (record.children?.length ?? 0) > 0;
    const patchSubtree = (node: IssueTreeNode): IssueTreeNode => ({
      ...node,
      include_in_analysis: checked,
      children: node.children.map(patchSubtree),
    });
    const patchTree = (nodes: IssueTreeNode[]): IssueTreeNode[] => nodes.map(n => {
      if (n.id === record.id) {
        return recursive ? patchSubtree(n) : { ...n, include_in_analysis: checked };
      }
      return { ...n, children: patchTree(n.children) };
    });
    qc.setQueryData<IssueTreeNode[]>(treeQueryKey, (old) => old ? patchTree(old) : old);
    setIncludeMut.mutate(
      { issueId: record.id, include: checked, recursive },
      {
        onError: (err) => {
          notification.error({ message: 'Ошибка', description: err.message });
          issueTree.refetch();
        },
      },
    );
  };

  const handleResize = (colKey: string) =>
    (_: SyntheticEvent, { size }: { size: { width: number; height: number } }) => {
      setWidths(w => ({ ...w, [colKey]: size.width }));
    };

  const setPendingCategory = (issueId: string, code: string | null) => {
    setPendingCats(prev => {
      const next = new Map(prev);
      next.set(issueId, code);
      return next;
    });
  };

  const applyBulkCategory = () => {
    if (!bulkCategory || selectedIds.length === 0) return;
    setPendingCats(prev => {
      const next = new Map(prev);
      selectedIds.forEach(id => next.set(id, bulkCategory));
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
      const assignments = new Map<string, string | null>();
      for (const [code, ids] of groups) {
        const res = await batchCategoryMut.mutateAsync({ issueIds: ids, categoryCode: code });
        ids.forEach(id => assignments.set(id, code));
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

      const total = pendingCats.size;
      setPendingCats(new Map());
      if (archivedIds.size > 0) {
        notification.success({
          message: `Сохранено категорий: ${total}`,
          description: `В архив перемещено: ${archivedIds.size} — автоматически исключены из анализа.`,
        });
      } else {
        message.success(`Сохранено категорий: ${total}`);
      }
    } catch (e) {
      notification.error({ message: 'Ошибка сохранения', description: (e as Error).message });
    }
  };

  const baseColumns = [
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
      render: (s: string) => <Text>{s}</Text>,
    },
    {
      title: 'Статус',
      dataIndex: 'status',
      key: 'status',
      width: widths.status,
      render: (v: string) => v ? <Tag>{v}</Tag> : null,
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
      title: 'Категория',
      key: 'category',
      width: widths.category,
      render: (_: unknown, record: TreeNodeWithChildren) => {
        if (record.issue_type === 'group') return null;
        if (record.is_context) return <Text type="secondary" style={{ fontSize: 11 }}>контекст</Text>;
        const pending = pendingCats.has(record.id);
        const value = pending ? (pendingCats.get(record.id) ?? undefined) : (record.assigned_category || undefined);
        const ancestorCat = !value ? record.__inheritedAssigned : null;
        const derivedCat = !value && !ancestorCat ? record.category : null;
        const placeholderCode = ancestorCat ?? derivedCat;
        const placeholderLabel = placeholderCode
          ? (ancestorCat ? '↑ ' : '') + (categoryLabels[placeholderCode] || placeholderCode)
          : 'Не назначена';
        return (
          <Select
            placeholder={placeholderLabel}
            value={value}
            onChange={(val) => setPendingCategory(record.id, val || null)}
            allowClear
            size="small"
            style={{
              width: '100%',
              opacity: !value && placeholderCode ? 0.6 : 1,
              boxShadow: pending ? `0 0 4px ${DARK_THEME.cyanPrimary}` : undefined,
            }}
            options={categoryOptions}
          />
        );
      },
    },
    {
      title: 'В анализ',
      key: 'include',
      width: widths.include,
      render: (_: unknown, record: IssueTreeNode) => {
        if (record.issue_type === 'group') return null;
        return (
          <Checkbox
            checked={record.include_in_analysis}
            disabled={record.is_context}
            onChange={(e) => toggleInclude(record, e.target.checked)}
          />
        );
      },
    },
  ];

  const columns = baseColumns.map(col => ({
    ...col,
    onHeaderCell: () => ({ width: col.width, onResize: handleResize(col.key) }),
  }));

  const rowSelection = {
    selectedRowKeys: selectedIds,
    onChange: (keys: React.Key[]) => setSelectedIds(keys.map(String)),
    checkStrictly: false,
    getCheckboxProps: (record: TreeNodeWithChildren) => ({
      disabled: record.issue_type === 'group' || !!record.is_context,
    }),
  };

  const hasPending = pendingCats.size > 0;

  // Keys of all loaded, non-orphan, non-group nodes — for targeted refresh.
  const loadedKeys = useMemo(() => {
    const out: string[] = [];
    const walk = (nodes: IssueTreeNode[]) => {
      nodes.forEach(n => {
        if (n.issue_type !== 'group' && n.key) out.push(n.key);
        walk(n.children);
      });
    };
    walk(issueTree.data ?? []);
    return out;
  }, [issueTree.data]);

  const handleRefreshVisible = () => {
    if (loadedKeys.length === 0) return;
    refreshMut.mutate(loadedKeys, {
      onSuccess: (res) => {
        notification.success({
          message: 'Обновление с Jira завершено',
          description: res.message,
        });
        issueTree.refetch();
      },
      onError: (e) => notification.error({ message: 'Ошибка обновления', description: e.message }),
    });
  };

  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      <Space wrap>
        <Select
          mode="multiple"
          placeholder="Продуктовые команды"
          value={selectedTeams}
          onChange={handleTeamsChange}
          allowClear
          showSearch
          optionFilterProp="label"
          style={{ minWidth: 360 }}
          maxTagCount="responsive"
          options={(jiraTeams.data ?? []).map(t => ({ value: t, label: t }))}
          onDropdownVisibleChange={(open) => { if (open && !jiraTeams.data) jiraTeams.refetch(); }}
          loading={jiraTeams.isFetching}
        />
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
        {issueTree.isFetching ? (
          <Button
            danger
            icon={<CloseOutlined />}
            onClick={() => qc.cancelQueries({ queryKey: treeQueryKey })}
          >
            Отменить загрузку
          </Button>
        ) : (
          <Button
            type="primary"
            icon={<SyncOutlined />}
            disabled={selectedTeams.length === 0}
            onClick={() => issueTree.refetch()}
          >
            Получить перечень задач
          </Button>
        )}
        <Button
          icon={<CheckOutlined />}
          disabled={selectedIds.length === 0}
          onClick={() => setBulkModalOpen(true)}
        >
          Установить категорию отмеченным ({selectedIds.length})
        </Button>
        <Popconfirm
          title="Обновить с Jira видимые задачи"
          description={
            <div style={{ maxWidth: 320 }}>
              Перечитает с Jira {loadedKeys.length} загруженных задач,
              не создавая новых. Нужно чтобы подтянуть «Статус изменён»
              и другие поля у уже существующих задач.
            </div>
          }
          icon={<ExclamationCircleOutlined style={{ color: '#faad14' }} />}
          okText="Запустить"
          cancelText="Отмена"
          onConfirm={handleRefreshVisible}
          disabled={loadedKeys.length === 0 || refreshMut.isPending}
        >
          <Button
            icon={<ReloadOutlined spin={refreshMut.isPending} />}
            disabled={loadedKeys.length === 0 || refreshMut.isPending}
            loading={refreshMut.isPending}
          >
            Обновить с Jira ({loadedKeys.length})
          </Button>
        </Popconfirm>
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
        onChange={(k) => setInnerTab(k as 'stack' | 'sorted')}
        items={[
          { key: 'stack', label: `Стек задач к разбору (${countTriage(stackData, false)})` },
          { key: 'sorted', label: `Разобранные (${countTriage(sortedData, true)})` },
        ]}
      />
      <Table<TreeNodeWithChildren>
        dataSource={tabData}
        columns={columns as never}
        components={{ header: { cell: ResizableTitle } }}
        rowKey="id"
        rowSelection={rowSelection}
        rowClassName={(record) => {
          const depth = Math.min(record.__depth ?? 0, 5);
          const hasKids = (record.children?.length ?? 0) > 0;
          const ctx = record.is_context ? ' tree-row-context' : '';
          return `tree-row-depth-${depth}${hasKids ? ' tree-row-has-children' : ''}${ctx}`;
        }}
        loading={issueTree.isFetching}
        pagination={false}
        size="small"
        expandable={{ defaultExpandAllRows: false }}
        scroll={{ y: 600 }}
      />
      <Modal
        title={`Установить категорию для ${selectedIds.length} задач`}
        open={bulkModalOpen}
        onCancel={() => { setBulkModalOpen(false); setBulkCategory(undefined); }}
        onOk={applyBulkCategory}
        okText="Применить"
        cancelText="Отмена"
        okButtonProps={{ disabled: !bulkCategory }}
      >
        <Text type="secondary">
          Категория будет отмечена как «к сохранению». Для применения нажмите «Сохранить».
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

  const handleFullSync = () => {
    const body = { project_keys: scopeKeys.length > 0 ? scopeKeys : undefined, incremental: false };
    fullSyncMut.mutate(body, {
      onSuccess: (res) => notification.success({ message: 'Полная синхронизация', description: res.message }),
      onError: (e) => notification.error({ message: 'Ошибка синхронизации', description: e.message }),
    });
  };

  const handleIncrementalSync = () => {
    const body = { project_keys: scopeKeys.length > 0 ? scopeKeys : undefined, incremental: true };
    incrementalSyncMut.mutate(body, {
      onSuccess: (res) => notification.success({ message: 'Обновление', description: res.message }),
      onError: (e) => notification.error({ message: 'Ошибка обновления', description: e.message }),
    });
  };

  const handleWorklogs = () => {
    worklogsMut.mutate(undefined, {
      onSuccess: () => {
        commentsMut.mutate(undefined, {
          onSuccess: (res) => notification.success({ message: 'Ворклоги и комментарии', description: res.message }),
          onError: (e) => notification.error({ message: 'Ошибка комментариев', description: e.message }),
        });
      },
      onError: (e) => notification.error({ message: 'Ошибка ворклогов', description: e.message }),
    });
  };

  const statusColumns = [
    { title: 'Сущность', dataIndex: 'entity', key: 'entity' },
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
            <Button
              type="primary"
              icon={<SyncOutlined spin={incrementalSyncMut.isPending} />}
              loading={incrementalSyncMut.isPending}
              onClick={handleIncrementalSync}
            >
              Обновить
            </Button>
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
              <Button
                icon={<SyncOutlined spin={fullSyncMut.isPending} />}
                loading={fullSyncMut.isPending}
              >
                Полная синхронизация
              </Button>
            </Popconfirm>
            <Button
              icon={<SyncOutlined spin={worklogsMut.isPending || commentsMut.isPending} />}
              loading={worklogsMut.isPending || commentsMut.isPending}
              onClick={handleWorklogs}
            >
              Ворклоги
            </Button>
          </Space>
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
          rowKey="entity"
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
    <Space orientation="vertical" size="large" style={{ width: '100%' }}>
      <ConnectionCard />
      <ScopeOverview />
      <Tabs
        items={[
          { key: 'projects', label: 'Разделы задач', children: <TaskSectionsTab /> },
          { key: 'categories', label: 'Настройка категорий задач', children: <CategoryConfigTab /> },
          { key: 'sync', label: 'Синхронизация', children: <SyncControls /> },
        ]}
        defaultActiveKey="projects"
      />
    </Space>
  );
}
