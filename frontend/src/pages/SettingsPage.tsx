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
} from 'antd';
import {
  CloudDownloadOutlined,
  PlusOutlined,
  DeleteOutlined,
} from '@ant-design/icons';
import dayjs from 'dayjs';
import ConnectionCard from '../components/ConnectionCard';
import ScopeAdmin from '../components/ScopeAdmin';
import JiraFieldsCard from '../components/JiraFieldsCard';
import HierarchyRulesTab from '../components/HierarchyRulesTab';
import PageHeader from '../components/shared/PageHeader';
import {
  useProductionCalendarYear,
  useSyncProductionCalendarYear,
  useUpsertProductionCalendarDay,
  useDeleteProductionCalendarDay,
} from '../hooks/useProductionCalendar';
import type { ProductionCalendarDayResponse } from '../types/api';

const TAB_KEYS = ['connection', 'scope', 'fields', 'hierarchy', 'calendar'] as const;
type TabKey = typeof TAB_KEYS[number];

function readHashKey(): TabKey {
  const raw = window.location.hash.replace('#', '');
  return TAB_KEYS.includes(raw as TabKey) ? (raw as TabKey) : 'connection';
}

export default function SettingsPage() {
  const [activeKey, setActiveKey] = useState<TabKey>(readHashKey);

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
          { key: 'calendar', label: 'Производственный календарь', children: <ProductionCalendarTab /> },
        ]}
      />
    </>
  );
}

function ProductionCalendarTab() {
  const { notification } = App.useApp();
  const [year, setYear] = useState<number>(dayjs().year());
  const q = useProductionCalendarYear(year);
  const sync = useSyncProductionCalendarYear();
  const upsert = useUpsertProductionCalendarDay();
  const del = useDeleteProductionCalendarDay();
  const [addOpen, setAddOpen] = useState(false);
  const [form] = Form.useForm();

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
        <Button icon={<PlusOutlined />} onClick={() => setAddOpen(true)}>
          Добавить день
        </Button>
      </Space>
      <Table<ProductionCalendarDayResponse>
        dataSource={q.data}
        rowKey="date"
        loading={q.isLoading}
        pagination={false}
        size="small"
        columns={[
          {
            title: 'Дата',
            dataIndex: 'date',
            render: (v: string) => dayjs(v).format('DD.MM.YYYY'),
          },
          { title: 'Тип', dataIndex: 'kind' },
          {
            title: 'Рабочий?',
            dataIndex: 'is_workday',
            render: (v: boolean) => (v ? 'да' : 'нет'),
          },
          { title: 'Примечание', dataIndex: 'note' },
          { title: 'Источник', dataIndex: 'source' },
          {
            title: '',
            width: 80,
            render: (_: unknown, r: ProductionCalendarDayResponse) =>
              r.source === 'manual' ? (
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
              ) : null,
          },
        ]}
      />
      <Modal
        title="Добавить/изменить день"
        open={addOpen}
        onCancel={() => {
          setAddOpen(false);
          form.resetFields();
        }}
        onOk={() => form.submit()}
        confirmLoading={upsert.isPending}
      >
        <Form
          form={form}
          layout="vertical"
          onFinish={(vals) => {
            upsert.mutate(
              {
                date: vals.date.format('YYYY-MM-DD'),
                is_workday: vals.is_workday,
                kind: vals.kind,
                note: vals.note ?? null,
              },
              {
                onSuccess: () => {
                  setAddOpen(false);
                  form.resetFields();
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
            <DatePicker format="DD.MM.YYYY" />
          </Form.Item>
          <Form.Item
            name="is_workday"
            label="Рабочий?"
            valuePropName="checked"
            initialValue={false}
          >
            <Switch />
          </Form.Item>
          <Form.Item
            name="kind"
            label="Тип"
            initialValue="holiday"
            rules={[{ required: true }]}
          >
            <Select
              options={[
                { value: 'holiday', label: 'Праздник' },
                { value: 'weekend', label: 'Выходной' },
                { value: 'preholiday', label: 'Предпраздничный' },
                { value: 'workday_moved', label: 'Перенесённый рабочий' },
              ]}
            />
          </Form.Item>
          <Form.Item name="note" label="Примечание">
            <Input />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
