import { useState, useMemo, useEffect } from 'react';
import {
  Button, Card, Space, Table, Tag, App, Input, Switch,
  Select, Typography, Modal,
} from 'antd';
import {
  SyncOutlined, SearchOutlined,
  CheckOutlined, CloseOutlined,
  SettingOutlined,
} from '@ant-design/icons';
import { useQueryClient } from '@tanstack/react-query';
import { getJiraProjects } from '../api/sync';
import { useSaveGenericSetting, useGenericSetting } from '../hooks/useSettings';
import {
  useJiraProjects, useBatchScopeProjects,
  useJiraTeams, useJiraFields,
} from '../hooks/useSync';
import { useScopeProjects } from '../hooks/useScope';
import { DARK_THEME } from '../utils/constants';
import type { JiraProjectItem } from '../types/api';

const { Text } = Typography;

export default function TaskSectionsTab() {
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
          notification.success({ title: 'Scope обновлён', description: `Добавлено: ${res.added}, удалено: ${res.removed}` });
          setPendingAdd(new Set());
          setPendingRemove(new Set());
        },
        onError: (e) => notification.error({ title: 'Ошибка', description: e.message }),
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
      <Space orientation="vertical" style={{ width: '100%' }}>
        <Space wrap>
          <Select
            placeholder="Команда (продуктовая или участвующая)"
            value={selectedTeam}
            onChange={handleTeamChange}
            allowClear
            style={{ width: 320 }}
            options={(jiraTeams.data ?? []).map(t => ({ value: t, label: t }))}
            onOpenChange={(open) => { if (open && !jiraTeams.data) jiraTeams.refetch(); }}
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
        <Space orientation="vertical" style={{ width: '100%' }} size="middle">
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
