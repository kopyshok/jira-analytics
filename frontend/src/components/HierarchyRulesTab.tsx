import { useMemo, useState } from 'react';
import { Table, Button, Space, Tag, Drawer, Form, Input, Select, Switch, InputNumber, Popconfirm, App, Typography } from 'antd';
import { PlusOutlined, DeleteOutlined, ArrowUpOutlined, ArrowDownOutlined } from '@ant-design/icons';
import {
  useHierarchyRules,
  useCreateHierarchyRule,
  useUpdateHierarchyRule,
  useDeleteHierarchyRule,
  useReorderHierarchyRules,
} from '../hooks/useHierarchyRules';
import { useProjects } from '../hooks/useBacklog';
import { useJiraIssueTypes } from '../hooks/useSync';
import type { HierarchyRule, HierarchyRuleCreate } from '../types/api';

const { Text } = Typography;

type FormState = Omit<HierarchyRuleCreate, 'priority'> & { id?: string; priority?: number };

const EMPTY_FORM: FormState = {
  priority: undefined,
  project_key: null,
  issue_type: null,
  require_no_parent: false,
  is_container: true,
  is_enabled: true,
  description: null,
};

export default function HierarchyRulesTab() {
  const { message } = App.useApp();
  const rules = useHierarchyRules();
  const createMut = useCreateHierarchyRule();
  const updateMut = useUpdateHierarchyRule();
  const deleteMut = useDeleteHierarchyRule();
  const reorderMut = useReorderHierarchyRules();
  const projects = useProjects();
  const issueTypes = useJiraIssueTypes();

  const projectOptions = useMemo(
    () => (projects.data ?? []).map(p => ({ value: p.key, label: `${p.key} — ${p.name}` })),
    [projects.data],
  );
  // Jira может отдать меньше типов, чем встречается в уже сохранённых правилах
  // (seed-правила могут ссылаться на тип, который в Jira отсутствует или ещё
  // не прогружен). Объединяем каталог Jira с типами из уже существующих
  // правил — так select не «теряет» текущее значение при редактировании.
  const typeOptions = useMemo(() => {
    const jira = new Set(issueTypes.data ?? []);
    (rules.data ?? []).forEach(r => { if (r.issue_type) jira.add(r.issue_type); });
    return Array.from(jira).sort().map(t => ({ value: t, label: t }));
  }, [issueTypes.data, rules.data]);

  const [drawerOpen, setDrawerOpen] = useState(false);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);

  const openCreate = () => { setForm(EMPTY_FORM); setDrawerOpen(true); };
  const openEdit = (r: HierarchyRule) => { setForm({ ...r }); setDrawerOpen(true); };

  const saveForm = async () => {
    const payload: HierarchyRuleCreate = {
      priority: form.priority ?? 100,
      project_key: form.project_key || null,
      issue_type: form.issue_type || null,
      require_no_parent: form.require_no_parent,
      is_container: form.is_container,
      is_enabled: form.is_enabled,
      description: form.description || null,
    };
    try {
      if (form.id) {
        await updateMut.mutateAsync({ id: form.id, body: payload });
      } else {
        await createMut.mutateAsync(payload);
      }
      setDrawerOpen(false);
      message.success('Сохранено');
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  const move = (id: string, delta: -1 | 1) => {
    const list = rules.data ?? [];
    const idx = list.findIndex(r => r.id === id);
    if (idx < 0) return;
    const swapIdx = idx + delta;
    if (swapIdx < 0 || swapIdx >= list.length) return;
    const reordered = list.slice();
    [reordered[idx], reordered[swapIdx]] = [reordered[swapIdx], reordered[idx]];
    reorderMut.mutate(reordered.map(r => r.id));
  };

  const columns = [
    { title: 'Приоритет', dataIndex: 'priority', key: 'priority', width: 90 },
    {
      title: 'Проект', dataIndex: 'project_key', key: 'project_key', width: 120,
      render: (v: string | null) => v ? <Tag color="blue">{v}</Tag> : <Text type="secondary">любой</Text>,
    },
    {
      title: 'Тип задачи', dataIndex: 'issue_type', key: 'issue_type', width: 180,
      render: (v: string | null) => v ? <Tag>{v}</Tag> : <Text type="secondary">любой</Text>,
    },
    {
      title: 'Без родителя', dataIndex: 'require_no_parent', key: 'require_no_parent', width: 120,
      render: (v: boolean) => v ? <Tag color="geekblue">да</Tag> : <Text type="secondary">—</Text>,
    },
    {
      title: 'Контейнер', dataIndex: 'is_container', key: 'is_container', width: 110,
      render: (v: boolean) => v ? <Tag color="green">да</Tag> : <Tag color="red">нет</Tag>,
    },
    {
      title: 'Активно', dataIndex: 'is_enabled', key: 'is_enabled', width: 90,
      render: (v: boolean, r: HierarchyRule) => (
        <Switch
          checked={v}
          size="small"
          onChange={checked => updateMut.mutate({ id: r.id, body: { is_enabled: checked } })}
        />
      ),
    },
    { title: 'Описание', dataIndex: 'description', key: 'description', ellipsis: true },
    {
      title: '', key: 'actions', width: 160,
      render: (_: unknown, r: HierarchyRule) => (
        <Space size={4}>
          <Button size="small" icon={<ArrowUpOutlined />} onClick={() => move(r.id, -1)} />
          <Button size="small" icon={<ArrowDownOutlined />} onClick={() => move(r.id, 1)} />
          <Button size="small" onClick={() => openEdit(r)}>✎</Button>
          <Popconfirm title="Удалить правило?" onConfirm={() => deleteMut.mutate(r.id)} okText="Да" cancelText="Нет">
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Space orientation="vertical" style={{ width: '100%' }} size="middle">
      <Space>
        <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>
          Правило
        </Button>
        <Text type="secondary">
          Первое совпавшее правило определяет, считается ли корневая задача контейнером.
        </Text>
      </Space>
      <Table<HierarchyRule>
        dataSource={rules.data ?? []}
        columns={columns as never}
        rowKey="id"
        size="small"
        pagination={false}
        loading={rules.isLoading}
      />
      <Drawer
        title={form.id ? 'Редактировать правило' : 'Новое правило'}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        styles={{ wrapper: { width: 420 } }}
        extra={
          <Space>
            <Button onClick={() => setDrawerOpen(false)}>Отмена</Button>
            <Button type="primary" onClick={saveForm} loading={createMut.isPending || updateMut.isPending}>
              Сохранить
            </Button>
          </Space>
        }
      >
        <Form layout="vertical">
          <Form.Item label="Приоритет (меньше — раньше)">
            <InputNumber
              min={0}
              value={form.priority}
              onChange={v => setForm(f => ({ ...f, priority: (v as number | null) ?? undefined }))}
              style={{ width: '100%' }}
              placeholder="100"
            />
          </Form.Item>
          <Form.Item label="Проект (пусто = любой)">
            <Select
              value={form.project_key ?? undefined}
              onChange={v => setForm(f => ({ ...f, project_key: v ?? null }))}
              allowClear
              showSearch
              placeholder="Любой проект"
              options={projectOptions}
              loading={projects.isLoading}
              optionFilterProp="label"
              style={{ width: '100%' }}
            />
          </Form.Item>
          <Form.Item
            label="Тип задачи (пусто = любой)"
            extra={issueTypes.isError ? <Text type="warning">Не удалось получить типы из Jira — проверь подключение</Text> : undefined}
          >
            <Select
              value={form.issue_type ?? undefined}
              onChange={v => setForm(f => ({ ...f, issue_type: v ?? null }))}
              allowClear
              showSearch
              placeholder="Любой тип"
              options={typeOptions}
              loading={issueTypes.isLoading}
              optionFilterProp="label"
              style={{ width: '100%' }}
            />
          </Form.Item>
          <Form.Item label="Только при отсутствии родителя">
            <Switch
              checked={form.require_no_parent}
              onChange={v => setForm(f => ({ ...f, require_no_parent: v }))}
            />
          </Form.Item>
          <Form.Item label="Считать контейнером">
            <Switch
              checked={form.is_container}
              onChange={v => setForm(f => ({ ...f, is_container: v }))}
            />
          </Form.Item>
          <Form.Item label="Активно">
            <Switch
              checked={form.is_enabled}
              onChange={v => setForm(f => ({ ...f, is_enabled: v }))}
            />
          </Form.Item>
          <Form.Item label="Описание">
            <Input.TextArea
              rows={2}
              value={form.description ?? ''}
              onChange={e => setForm(f => ({ ...f, description: e.target.value || null }))}
            />
          </Form.Item>
        </Form>
      </Drawer>
    </Space>
  );
}
