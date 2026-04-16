import { useState, useMemo } from 'react';
import {
  Button, Card, Space, Table, Tag, App, Input, Switch,
  Tabs, Select, Typography, Modal, Checkbox,
} from 'antd';
import {
  SyncOutlined, ApiOutlined, ReloadOutlined, SearchOutlined,
  CheckOutlined, CloseOutlined,
  SaveOutlined, SettingOutlined,
} from '@ant-design/icons';
import { useQueryClient } from '@tanstack/react-query';
import { testConnection, getJiraProjects } from '../api/sync';
import { useJiraSettings, useSaveJiraSettings, useTestJiraCredentials, useSaveGenericSetting, useGenericSetting } from '../hooks/useSettings';
import {
  useSyncStatus, useSyncMutation, useRecalculateMapping,
  useJiraProjects, useBatchScopeProjects,
  useJiraTeams, useJiraFields,
} from '../hooks/useSync';
import {
  useScopeProjects, useRemoveScopeProject,
} from '../hooks/useScope';
import { formatDate } from '../utils/format';
import { DARK_THEME } from '../utils/constants';
import { useCategories } from '../hooks/useCategories';
import { useIssueTree, useSetIssueCategory, useSetIssueInclude } from '../hooks/useIssueTree';
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
  const [loadingAll, setLoadingAll] = useState(false);
  const jiraProjects = useJiraProjects(search, selectedTeam);
  const scopeProjects = useScopeProjects();
  const batchMutation = useBatchScopeProjects();
  const jiraTeams = useJiraTeams();
  const jiraFields = useJiraFields();
  const saveFieldSetting = useSaveGenericSetting();
  const productField = useGenericSetting('jira_team_field_id');
  const participatingField = useGenericSetting('jira_participating_teams_field_id');
  const [showFieldModal, setShowFieldModal] = useState(false);
  const [productFieldDraft, setProductFieldDraft] = useState<string | undefined>();
  const [participatingFieldDraft, setParticipatingFieldDraft] = useState<string | undefined>();

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
    setSelectedTeam(undefined);
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
            onChange={setSelectedTeam}
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

function CategoryConfigTab() {
  const { notification } = App.useApp();
  const [selectedTeam, setSelectedTeam] = useState<string | undefined>();
  const scopeProjects = useScopeProjects();
  const scopeKeys = (scopeProjects.data ?? []).map(p => p.jira_project_key).join(',');
  const issueTree = useIssueTree({ project_keys: scopeKeys || undefined, team: selectedTeam });
  const jiraTeams = useJiraTeams();
  const setCategoryMut = useSetIssueCategory();
  const setIncludeMut = useSetIssueInclude();
  const { options: categoryOptions, labels: categoryLabels } = useCategories();

  // Flatten tree for Ant Design expandable table
  const flattenTree = (nodes: IssueTreeNode[]): (IssueTreeNode & { _children?: IssueTreeNode[] })[] => {
    return nodes.map(n => ({
      ...n,
      children: n.children.length > 0 ? flattenTree(n.children) : undefined,
      _children: n.children,
    })) as (IssueTreeNode & { _children?: IssueTreeNode[] })[];
  };

  const treeData = useMemo(() => flattenTree(issueTree.data ?? []), [issueTree.data]);

  // Find inherited category by walking up (simple: show assigned_category or category)
  const getDisplayCategory = (node: IssueTreeNode) => {
    if (node.assigned_category) return { code: node.assigned_category, inherited: false };
    if (node.category) return { code: node.category, inherited: true };
    return null;
  };

  const columns = [
    {
      title: 'Задача',
      key: 'summary',
      render: (_: unknown, record: IssueTreeNode) => (
        <span>
          {record.key && <Text strong style={{ marginRight: 8 }}>{record.key}</Text>}
          <Text>{record.summary}</Text>
        </span>
      ),
    },
    {
      title: 'Статус',
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (v: string) => v ? <Tag>{v}</Tag> : null,
    },
    {
      title: 'Категория',
      key: 'category',
      width: 280,
      render: (_: unknown, record: IssueTreeNode) => {
        if (record.id === '__orphans__') return null;
        const display = getDisplayCategory(record);
        return (
          <Select
            placeholder={display?.inherited ? categoryLabels[display.code] || display.code : 'Не назначена'}
            value={record.assigned_category || undefined}
            onChange={(val) => setCategoryMut.mutate(
              { issueId: record.id, categoryCode: val || null },
              { onError: (e) => notification.error({ message: 'Ошибка', description: e.message }) },
            )}
            allowClear
            size="small"
            style={{
              width: '100%',
              opacity: display?.inherited && !record.assigned_category ? 0.6 : 1,
            }}
            options={categoryOptions}
          />
        );
      },
    },
    {
      title: 'В анализ',
      key: 'include',
      width: 80,
      render: (_: unknown, record: IssueTreeNode) => {
        if (record.id === '__orphans__') return null;
        return (
          <Checkbox
            checked={record.include_in_analysis}
            onChange={(e) => setIncludeMut.mutate(
              {
                issueId: record.id,
                include: e.target.checked,
                recursive: (record.children?.length ?? 0) > 0,
              },
              { onError: (err) => notification.error({ message: 'Ошибка', description: err.message }) },
            )}
          />
        );
      },
    },
  ];

  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      <Space wrap>
        <Select
          placeholder="Продуктовая команда"
          value={selectedTeam}
          onChange={setSelectedTeam}
          allowClear
          style={{ width: 280 }}
          options={(jiraTeams.data ?? []).map(t => ({ value: t, label: t }))}
          onDropdownVisibleChange={(open) => { if (open && !jiraTeams.data) jiraTeams.refetch(); }}
          loading={jiraTeams.isFetching}
        />
        <Button
          type="primary"
          icon={<SyncOutlined spin={issueTree.isFetching} />}
          onClick={() => issueTree.refetch()}
          loading={issueTree.isFetching}
        >
          Получить перечень задач
        </Button>
      </Space>
      <Table
        dataSource={treeData}
        columns={columns}
        rowKey="id"
        loading={issueTree.isFetching}
        pagination={false}
        size="small"
        expandable={{ defaultExpandAllRows: false }}
        scroll={{ y: 600 }}
      />
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
  const worklogsMut = useSyncMutation('worklogs');
  const commentsMut = useSyncMutation('comments');

  const handleFullSync = () => {
    const body = { project_keys: scopeKeys.length > 0 ? scopeKeys : undefined, incremental: false };
    fullSyncMut.mutate(body, {
      onSuccess: (res) => notification.success({ message: 'Полная синхронизация', description: res.message }),
      onError: (e) => notification.error({ message: 'Ошибка синхронизации', description: e.message }),
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
              icon={<SyncOutlined spin={fullSyncMut.isPending} />}
              loading={fullSyncMut.isPending}
              onClick={handleFullSync}
            >
              Полная синхронизация
            </Button>
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
