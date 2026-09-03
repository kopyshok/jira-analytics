import { useState, useEffect } from 'react';
import {
  Menu,
  Grid,
  App,
  Space,
  Button,
  Table,
  Modal,
  Form,
  Input,
  InputNumber,
  Switch,
  Select,
  DatePicker,
  Popconfirm,
  Tag,
} from 'antd';
import {
  CloudDownloadOutlined,
  PlusOutlined,
  DeleteOutlined,
  EditOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import settingsHelp from '../../../docs/help/settings.md?raw';
import { useRegisterHelp } from '../contexts/HelpContext';
import ConnectionCard from '../components/ConnectionCard';
import ScopeAdmin from '../components/ScopeAdmin';
import JiraFieldsCard from '../components/JiraFieldsCard';
import HierarchyRulesTab from '../components/HierarchyRulesTab';
import PlanningSettingsTab from '../components/settings/PlanningSettingsTab';
import AbsenceReasonsTab from '../components/AbsenceReasonsTab';
import CategoriesTab from '../components/CategoriesTab';
import WorkTypesTab from '../components/settings/WorkTypesTab';
import TeamsRegistryTab from '../components/settings/TeamsRegistryTab';
import KpiSettingsTab from '../components/settings/kpi/KpiSettingsTab';
import TeamDeskSettingsTab from '../components/settings/TeamDeskSettingsTab';
import { AITab } from '../components/settings/AITab';
import VisibilityTab from '../components/settings/VisibilityTab';
import PageHeader from '../components/shared/PageHeader';
import { useAuth } from '../hooks/useAuth';
import UsersTab from './settings/UsersTab';
import FeedbackAdminTab from '../components/feedback/FeedbackAdminTab';
import UsageTab from '../components/admin/usage/UsageTab';
import ReleaseNotesAdminTab from '../components/settings/ReleaseNotesAdminTab';
import DbExportTab from '../components/settings/DbExportTab';
import ServerErrorsTab from '../components/settings/ServerErrorsTab';
import {
  useProductionCalendarYear,
  useSyncProductionCalendarYear,
  useUpsertProductionCalendarDay,
  useDeleteProductionCalendarDay,
} from '../hooks/useProductionCalendar';
import type { ProductionCalendarDayResponse } from '../types/api';

type Section = { key: string; label: string; adminOnly?: boolean; render: () => React.ReactNode };
type SectionGroup = { title: string; items: Section[] };

const GROUPS: SectionGroup[] = [
  {
    title: 'Подключение',
    items: [
      { key: 'connection', label: 'Подключение к Jira', render: () => <ConnectionCard /> },
      { key: 'scope', label: 'Проекты в scope', render: () => <ScopeAdmin /> },
      { key: 'fields', label: 'Поля Jira', render: () => <JiraFieldsCard /> },
    ],
  },
  {
    title: 'Справочники',
    items: [
      { key: 'teams', label: 'Команды и группы', render: () => <TeamsRegistryTab /> },
      { key: 'hierarchy', label: 'Правила иерархии', render: () => <HierarchyRulesTab /> },
      { key: 'planning', label: 'Планирование', render: () => <PlanningSettingsTab /> },
      { key: 'reasons', label: 'Причины отсутствий', render: () => <AbsenceReasonsTab /> },
      { key: 'categories', label: 'Категории работ', render: () => <CategoriesTab /> },
      { key: 'worktypes', label: 'Виды работ', render: () => <WorkTypesTab /> },
      { key: 'calendar', label: 'Производственный календарь', render: () => <ProductionCalendarTab /> },
      { key: 'kpi', label: 'KPI', render: () => <KpiSettingsTab /> },
      { key: 'team-desk', label: 'Стол тимлида', render: () => <TeamDeskSettingsTab /> },
    ],
  },
  {
    title: 'Доступ',
    items: [
      { key: 'users', label: 'Пользователи', adminOnly: true, render: () => <UsersTab /> },
      { key: 'visibility', label: 'Видимость разделов', render: () => <VisibilityTab /> },
    ],
  },
  {
    title: 'Администрирование',
    items: [
      { key: 'ai', label: 'AI', render: () => <AITab /> },
      { key: 'feedback', label: 'Обратная связь', adminOnly: true, render: () => <FeedbackAdminTab /> },
      { key: 'usage', label: 'Использование', adminOnly: true, render: () => <UsageTab /> },
      { key: 'whats-new', label: 'Что нового', adminOnly: true, render: () => <ReleaseNotesAdminTab /> },
      { key: 'db-export', label: 'Выгрузка базы', adminOnly: true, render: () => <DbExportTab /> },
      { key: 'errors', label: 'Ошибки сервиса', adminOnly: true, render: () => <ServerErrorsTab /> },
    ],
  },
];

function readHashKey(available: Section[]): string {
  const raw = window.location.hash.replace('#', '');
  return available.some((s) => s.key === raw) ? raw : available[0].key;
}

export default function SettingsPage() {
  const { user } = useAuth();
  const screens = Grid.useBreakpoint();
  useRegisterHelp('Настройки сервиса', settingsHelp);

  const isAdmin = user?.role === 'admin';
  const groups = GROUPS.map((g) => ({
    ...g,
    items: g.items.filter((s) => isAdmin || !s.adminOnly),
  })).filter((g) => g.items.length > 0);
  const sections = groups.flatMap((g) => g.items);

  const [activeKey, setActiveKey] = useState<string>(() => readHashKey(sections));

  useEffect(() => {
    const handler = () => setActiveKey(readHashKey(sections));
    window.addEventListener('hashchange', handler);
    return () => window.removeEventListener('hashchange', handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onChange = (k: string) => {
    setActiveKey(k);
    window.location.hash = k;
  };

  const active = sections.find((s) => s.key === activeKey) ?? sections[0];
  const narrow = !screens.md;

  return (
    <>
      <PageHeader
        eyebrow="Данные"
        title="Настройки"
        subtitle="Подключение к Jira, состав проектов, справочники, доступ и администрирование"
      />
      <div
        style={{
          display: 'flex',
          flexDirection: narrow ? 'column' : 'row',
          gap: narrow ? 12 : 24,
          alignItems: 'flex-start',
        }}
      >
        {narrow ? (
          <Select
            value={active.key}
            onChange={onChange}
            style={{ width: '100%' }}
            options={groups.map((g) => ({
              label: g.title,
              options: g.items.map((s) => ({ value: s.key, label: s.label })),
            }))}
          />
        ) : (
          <Menu
            mode="inline"
            selectedKeys={[active.key]}
            onClick={({ key }) => onChange(key)}
            style={{ width: 248, flex: 'none', position: 'sticky', top: 16, background: 'transparent' }}
            items={groups.map((g) => ({
              key: g.title,
              type: 'group' as const,
              label: g.title,
              children: g.items.map((s) => ({ key: s.key, label: s.label })),
            }))}
          />
        )}
        <div style={{ flex: 1, minWidth: 0, width: '100%' }}>{active.render()}</div>
      </div>
    </>
  );
}

const KIND_OPTIONS = [
  { value: 'workday', label: 'Рабочий', color: 'default' },
  { value: 'weekend', label: 'Выходной', color: 'blue' },
  { value: 'holiday', label: 'Праздник', color: 'red' },
  { value: 'preholiday', label: 'Предпраздничный', color: 'orange' },
  { value: 'workday_moved', label: 'Перенесённый рабочий', color: 'green' },
] as const;

const KIND_META: Record<string, { label: string; color: string }> = Object.fromEntries(
  KIND_OPTIONS.map((o) => [o.value, { label: o.label, color: o.color }]),
);

function kindLabel(kind: string): string {
  return KIND_META[kind]?.label ?? kind;
}

function kindColor(kind: string): string {
  return KIND_META[kind]?.color ?? 'default';
}

function ProductionCalendarTab() {
  const { notification } = App.useApp();
  const [year, setYear] = useState<number>(dayjs().year());
  const q = useProductionCalendarYear(year);
  const sync = useSyncProductionCalendarYear();
  const upsert = useUpsertProductionCalendarDay();
  const del = useDeleteProductionCalendarDay();
  const [editOpen, setEditOpen] = useState(false);
  const [editMode, setEditMode] = useState<'add' | 'edit'>('add');
  const [form] = Form.useForm();

  const openAdd = () => {
    setEditMode('add');
    form.resetFields();
    form.setFieldsValue({ is_workday: false, kind: 'holiday' });
    setEditOpen(true);
  };

  const openEdit = (r: ProductionCalendarDayResponse) => {
    setEditMode('edit');
    form.setFieldsValue({
      date: dayjs(r.date),
      is_workday: r.is_workday,
      kind: r.kind,
      hours: r.hours,
      note: r.note ?? undefined,
    });
    setEditOpen(true);
  };

  const handleClose = () => {
    setEditOpen(false);
    form.resetFields();
  };

  const toggleWorkday = (r: ProductionCalendarDayResponse, checked: boolean) => {
    upsert.mutate(
      {
        date: r.date,
        is_workday: checked,
        kind: checked
          ? r.kind === 'weekend' || r.kind === 'holiday'
            ? 'workday_moved'
            : r.kind
          : r.kind === 'workday' || r.kind === 'workday_moved' || r.kind === 'preholiday'
            ? 'weekend'
            : r.kind,
        note: r.note,
      },
      {
        onError: (e) =>
          notification.error({ title: 'Ошибка', description: e.message }),
      },
    );
  };

  return (
    <Space orientation="vertical" style={{ width: '100%' }}>
      <Space wrap>
        <InputNumber
          value={year}
          min={2020}
          max={2035}
          onChange={(v) => v && setYear(v)}
        />
        <Popconfirm
          title={`Загрузить ${year} из xmlcalendar.ru?`}
          okText="Загрузить"
          cancelText="Отмена"
          onConfirm={() =>
            sync.mutate(year, {
              onSuccess: (s) =>
                notification.success({
                  title: 'Календарь обновлён',
                  description: `Добавлено: ${s.inserted}, обновлено: ${s.updated}, ручных пропущено: ${s.skipped_manual}`,
                }),
              onError: (e) =>
                notification.error({ title: 'Ошибка', description: e.message }),
            })
          }
        >
          <Button loading={sync.isPending} icon={<CloudDownloadOutlined />}>
            Загрузить с xmlcalendar.ru
          </Button>
        </Popconfirm>
        <Button icon={<PlusOutlined />} onClick={openAdd}>
          Добавить день
        </Button>
      </Space>
      <Table<ProductionCalendarDayResponse>
        dataSource={q.data}
        rowKey="date"
        loading={q.isLoading}
        pagination={{
          defaultPageSize: 50,
          showSizeChanger: true,
          pageSizeOptions: [20, 50, 100, 200, 400],
          showTotal: (total) => `Всего: ${total}`,
        }}
        size="small"
        columns={[
          {
            title: 'Дата',
            dataIndex: 'date',
            width: 130,
            render: (v: string) => dayjs(v).format('DD.MM.YYYY (dd)'),
          },
          {
            title: 'Тип',
            dataIndex: 'kind',
            width: 200,
            render: (k: string) => <Tag color={kindColor(k)}>{kindLabel(k)}</Tag>,
          },
          {
            title: 'Рабочий',
            dataIndex: 'is_workday',
            width: 120,
            render: (v: boolean, r: ProductionCalendarDayResponse) => (
              <Switch
                checked={v}
                checkedChildren="Да"
                unCheckedChildren="Нет"
                loading={upsert.isPending}
                onChange={(checked) => toggleWorkday(r, checked)}
              />
            ),
          },
          {
            title: 'Норма часов',
            dataIndex: 'hours',
            width: 120,
            align: 'right',
            sorter: (a, b) => a.hours - b.hours,
            render: (h: number) => h,
          },
          { title: 'Примечание', dataIndex: 'note' },
          {
            title: 'Источник',
            dataIndex: 'source',
            width: 120,
            render: (s: string) => (
              <Tag color={s === 'manual' ? 'purple' : 'default'}>
                {s === 'manual' ? 'ручной' : 'xmlcalendar'}
              </Tag>
            ),
          },
          {
            title: '',
            width: 110,
            render: (_: unknown, r: ProductionCalendarDayResponse) => (
              <Space size={4}>
                <Button
                  icon={<EditOutlined />}
                  size="small"
                  onClick={() => openEdit(r)}
                />
                {r.source === 'manual' && (
                  <Popconfirm
                    title="Удалить?"
                    onConfirm={() =>
                      del.mutate(r.date, {
                        onError: (e) =>
                          notification.error({
                            title: 'Ошибка',
                            description: e.message,
                          }),
                      })
                    }
                  >
                    <Button icon={<DeleteOutlined />} size="small" danger />
                  </Popconfirm>
                )}
              </Space>
            ),
          },
        ]}
      />
      <Modal
        title={editMode === 'edit' ? 'Изменить день' : 'Добавить день'}
        open={editOpen}
        onCancel={handleClose}
        onOk={() => form.submit()}
        confirmLoading={upsert.isPending}
      >
        <Form
          form={form}
          layout="vertical"
          onValuesChange={(changed) => {
            // При смене типа/рабочий-флага очищаем hours: иначе пре-заполненное
            // при открытии модалки старое значение уходит override'ом и ломает норму.
            if ('kind' in changed || 'is_workday' in changed) {
              form.setFieldValue('hours', undefined);
            }
          }}
          onFinish={(vals) => {
            upsert.mutate(
              {
                date: vals.date.format('YYYY-MM-DD'),
                is_workday: vals.is_workday,
                kind: vals.kind,
                hours: vals.hours ?? null,
                note: vals.note ?? null,
              },
              {
                onSuccess: () => {
                  handleClose();
                  notification.success({ title: 'Сохранено' });
                },
                onError: (e) =>
                  notification.error({
                    title: 'Ошибка',
                    description: e.message,
                  }),
              },
            );
          }}
        >
          <Form.Item name="date" label="Дата" rules={[{ required: true }]}>
            <DatePicker format="DD.MM.YYYY" disabled={editMode === 'edit'} />
          </Form.Item>
          <Form.Item
            name="is_workday"
            label="Рабочий"
            valuePropName="checked"
            initialValue={false}
          >
            <Switch checkedChildren="Да" unCheckedChildren="Нет" />
          </Form.Item>
          <Form.Item
            name="kind"
            label="Тип"
            rules={[{ required: true }]}
          >
            <Select
              options={KIND_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
            />
          </Form.Item>
          <Form.Item
            name="hours"
            label="Норма часов"
            tooltip="Оставьте пустым, чтобы пересчитать по правилу (Пн–Пт 8ч, предпразд. 7ч, выходной 0ч)"
          >
            <InputNumber min={0} max={24} step={0.5} style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="note" label="Примечание">
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
