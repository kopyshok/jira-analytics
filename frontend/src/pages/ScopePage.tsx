import { useState } from 'react';
import { Tabs, Table, Button, Input, Select, Space, Popconfirm, App } from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import {
  useScopeProjects, useAddScopeProject, useRemoveScopeProject,
  useScopeRoots, useAddScopeRoot, useRemoveScopeRoot,
  useOverrides, useAddOverride, useRemoveOverride,
} from '../hooks/useScope';
import { CATEGORY_LABELS } from '../utils/constants';

const categoryOptions = Object.entries(CATEGORY_LABELS).map(([value, label]) => ({ value, label }));

function ProjectsTab() {
  const { notification } = App.useApp();
  const { data, isLoading } = useScopeProjects();
  const add = useAddScopeProject();
  const remove = useRemoveScopeProject();
  const [key, setKey] = useState('');

  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      <Space>
        <Input placeholder="Ключ проекта (напр. PROJ)" value={key} onChange={(e) => setKey(e.target.value)} style={{ width: 250 }} />
        <Button
          icon={<PlusOutlined />}
          type="primary"
          disabled={!key.trim()}
          loading={add.isPending}
          onClick={() => add.mutate({ jira_project_key: key.trim() }, {
            onSuccess: () => { setKey(''); notification.success({ message: 'Проект добавлен' }); },
            onError: (e) => notification.error({ message: 'Ошибка', description: e.message }),
          })}
        >
          Добавить
        </Button>
      </Space>
      <Table
        dataSource={data}
        rowKey="id"
        loading={isLoading}
        pagination={false}
        size="small"
        columns={[
          { title: 'Ключ проекта', dataIndex: 'jira_project_key' },
          { title: 'Активен', dataIndex: 'is_enabled', render: (v: boolean) => v ? 'Да' : 'Нет' },
          {
            title: '', width: 50,
            render: (_, r) => (
              <Popconfirm title="Удалить?" onConfirm={() => remove.mutate(r.jira_project_key)}>
                <Button icon={<DeleteOutlined />} size="small" danger />
              </Popconfirm>
            ),
          },
        ]}
      />
    </Space>
  );
}

function RootsTab() {
  const { notification } = App.useApp();
  const { data, isLoading } = useScopeRoots();
  const add = useAddScopeRoot();
  const remove = useRemoveScopeRoot();
  const [issueKey, setIssueKey] = useState('');
  const [category, setCategory] = useState<string>('');

  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      <Space>
        <Input placeholder="Ключ задачи (напр. PROJ-123)" value={issueKey} onChange={(e) => setIssueKey(e.target.value)} style={{ width: 200 }} />
        <Select placeholder="Категория" value={category || undefined} onChange={setCategory} options={categoryOptions} style={{ width: 300 }} />
        <Button
          icon={<PlusOutlined />}
          type="primary"
          disabled={!issueKey.trim() || !category}
          loading={add.isPending}
          onClick={() => add.mutate({ jira_issue_key: issueKey.trim(), category_code: category }, {
            onSuccess: () => { setIssueKey(''); setCategory(''); notification.success({ message: 'Корень добавлен' }); },
            onError: (e) => notification.error({ message: 'Ошибка', description: e.message }),
          })}
        >
          Добавить
        </Button>
      </Space>
      <Table
        dataSource={data}
        rowKey="id"
        loading={isLoading}
        pagination={false}
        size="small"
        columns={[
          { title: 'Задача', dataIndex: 'jira_issue_key' },
          { title: 'Категория', dataIndex: 'category_code', render: (v: string) => CATEGORY_LABELS[v] || v },
          {
            title: '', width: 50,
            render: (_, r) => (
              <Popconfirm title="Удалить?" onConfirm={() => remove.mutate(r.id)}>
                <Button icon={<DeleteOutlined />} size="small" danger />
              </Popconfirm>
            ),
          },
        ]}
      />
    </Space>
  );
}

function OverridesTab() {
  const { notification } = App.useApp();
  const { data, isLoading } = useOverrides();
  const add = useAddOverride();
  const remove = useRemoveOverride();
  const [issueKey, setIssueKey] = useState('');
  const [category, setCategory] = useState<string>('');

  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      <Space>
        <Input placeholder="Ключ задачи" value={issueKey} onChange={(e) => setIssueKey(e.target.value)} style={{ width: 200 }} />
        <Select placeholder="Категория" value={category || undefined} onChange={setCategory} options={categoryOptions} style={{ width: 300 }} />
        <Button
          icon={<PlusOutlined />}
          type="primary"
          disabled={!issueKey.trim() || !category}
          loading={add.isPending}
          onClick={() => add.mutate({ jira_issue_key: issueKey.trim(), category_code: category }, {
            onSuccess: () => { setIssueKey(''); setCategory(''); notification.success({ message: 'Переопределение добавлено' }); },
            onError: (e) => notification.error({ message: 'Ошибка', description: e.message }),
          })}
        >
          Добавить
        </Button>
      </Space>
      <Table
        dataSource={data}
        rowKey="id"
        loading={isLoading}
        pagination={false}
        size="small"
        columns={[
          { title: 'Задача', dataIndex: 'jira_issue_key' },
          { title: 'Категория', dataIndex: 'category_code', render: (v: string) => CATEGORY_LABELS[v] || v },
          { title: 'Комментарий', dataIndex: 'comment' },
          {
            title: '', width: 50,
            render: (_, r) => (
              <Popconfirm title="Удалить?" onConfirm={() => remove.mutate(r.jira_issue_key)}>
                <Button icon={<DeleteOutlined />} size="small" danger />
              </Popconfirm>
            ),
          },
        ]}
      />
    </Space>
  );
}

export default function ScopePage() {
  return (
    <Tabs items={[
      { key: 'projects', label: 'Проекты', children: <ProjectsTab /> },
      { key: 'roots', label: 'Корневые элементы', children: <RootsTab /> },
      { key: 'overrides', label: 'Переопределения', children: <OverridesTab /> },
    ]} />
  );
}
