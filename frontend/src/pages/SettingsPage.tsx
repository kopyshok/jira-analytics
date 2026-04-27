import { useState, useEffect } from 'react';
import {
  Tabs,
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
import ConnectionCard from '../components/ConnectionCard';
import ScopeAdmin from '../components/ScopeAdmin';
import JiraFieldsCard from '../components/JiraFieldsCard';
import HierarchyRulesTab from '../components/HierarchyRulesTab';
import AbsenceReasonsTab from '../components/AbsenceReasonsTab';
import CategoriesTab from '../components/CategoriesTab';
import PageHeader from '../components/shared/PageHeader';
import { useAuth } from '../hooks/useAuth';
import UsersTab from './settings/UsersTab';
import {
  useProductionCalendarYear,
  useSyncProductionCalendarYear,
  useUpsertProductionCalendarDay,
  useDeleteProductionCalendarDay,
} from '../hooks/useProductionCalendar';
import type { ProductionCalendarDayResponse } from '../types/api';

const TAB_KEYS = ['connection', 'scope', 'fields', 'hierarchy', 'reasons', 'categories', 'calendar', 'users'] as const;
type TabKey = typeof TAB_KEYS[number];

function readHashKey(): TabKey {
  const raw = window.location.hash.replace('#', '');
  return TAB_KEYS.includes(raw as TabKey) ? (raw as TabKey) : 'connection';
}

export default function SettingsPage() {
  const [activeKey, setActiveKey] = useState<TabKey>(readHashKey);
  const { user } = useAuth();

  useEffect(() => {
    const handler = () => setActiveKey(readHashKey());
    window.addEventListener('hashchange', handler);
    return () => window.removeEventListener('hashchange', handler);
  }, []);

  const onChange = (k: string) => {
    setActiveKey(k as TabKey);
    window.location.hash = k;
  };

  return (
    <>
      <PageHeader
        eyebrow="Данные"
        title="Настройки"
        subtitle="Подключение к Jira, scope проектов, поля, правила иерархии, производственный календарь"
      />
      <Tabs
        activeKey={activeKey}
        onChange={onChange}
        items={[
          { key: 'connection', label: 'Подключение к Jira', children: <ConnectionCard /> },
          { key: 'scope', label: 'Проекты в scope', children: <ScopeAdmin /> },
          { key: 'fields', label: 'Поля Jira', children: <JiraFieldsCard /> },
          { key: 'hierarchy', label: 'Правила иерархии', children: <HierarchyRulesTab /> },
          { key: 'reasons', label: 'Причины отсутствий', children: <AbsenceReasonsTab /> },
          { key: 'categories', label: 'Категории работ', children: <CategoriesTab /> },
          { key: 'calendar', label: 'Производственный календарь', children: <ProductionCalendarTab /> },
          ...(user?.role === 'admin' ? [{ key: 'users', label: 'Пользователи', children: <UsersTab /> }] : []),
        ]}
      />
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
    <Space direction="vertical" style={{ width: '100%' }}>
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
