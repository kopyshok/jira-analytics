import { useState } from 'react';
import { Space, Card, Table, Button, Tag, Popconfirm, App, Modal, Form, Input, Progress } from 'antd';
import { PlusOutlined, DeleteOutlined } from '@ant-design/icons';
import QuarterYearSelect from '../components/shared/QuarterYearSelect';
import ExportButtons from '../components/shared/ExportButtons';
import { useScenarios, useGenerateScenario, useDeleteScenario } from '../hooks/usePlanning';
import { useQuarterYear } from '../hooks/useQuarterYear';
import { downloadScenarioXlsx, downloadScenarioPptx } from '../api/exports';
import { formatHours } from '../utils/format';
import type { ScenarioResponse, PlanningResultResponse, AllocationResponse } from '../types/api';

export default function PlanningPage() {
  const { notification } = App.useApp();
  const { year, quarter } = useQuarterYear();
  const { data: scenarios, isLoading } = useScenarios(year, quarter);
  const generate = useGenerateScenario();
  const del = useDeleteScenario();
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState<PlanningResultResponse | null>(null);
  const [form] = Form.useForm();

  const handleGenerate = (vals: { name: string }) => {
    generate.mutate({ name: vals.name, year: Number(year), quarter: Number(quarter) }, {
      onSuccess: (res) => {
        setOpen(false);
        form.resetFields();
        setResult(res);
        notification.success({ message: `Сценарий "${res.scenario_name}" создан` });
      },
      onError: (e) => notification.error({ message: 'Ошибка', description: e.message }),
    });
  };

  const capacityPercent = result ? Math.round((result.total_planned_hours / result.total_capacity_hours) * 100) : 0;

  return (
    <Space orientation="vertical" size="large" style={{ width: '100%' }}>
      <Space>
        <QuarterYearSelect />
        <Button icon={<PlusOutlined />} type="primary" onClick={() => { form.resetFields(); setOpen(true); }}>
          Сгенерировать сценарий
        </Button>
      </Space>

      <Modal title="Новый сценарий" open={open} onCancel={() => setOpen(false)} onOk={() => form.submit()} confirmLoading={generate.isPending}>
        <Form form={form} layout="vertical" onFinish={handleGenerate}>
          <Form.Item name="name" label="Название сценария" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <p>Год: {year}, Квартал: Q{quarter}</p>
        </Form>
      </Modal>

      <Card title="Сценарии">
        <Table<ScenarioResponse>
          dataSource={scenarios}
          rowKey="id"
          loading={isLoading}
          pagination={false}
          size="small"
          columns={[
            { title: 'Название', dataIndex: 'name' },
            { title: 'Квартал', dataIndex: 'quarter' },
            { title: 'Год', dataIndex: 'year' },
            {
              title: 'Действия',
              width: 200,
              render: (_, r) => (
                <Space>
                  <ExportButtons
                    onXlsx={() => downloadScenarioXlsx(r.id)}
                    onPptx={() => downloadScenarioPptx(r.id)}
                  />
                  <Popconfirm title="Удалить?" onConfirm={() => del.mutate(r.id)}>
                    <Button icon={<DeleteOutlined />} size="small" danger />
                  </Popconfirm>
                </Space>
              ),
            },
          ]}
        />
      </Card>

      {result && (
        <Card title={`Результат: ${result.scenario_name}`}>
          <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
            <Space size="large">
              <div>
                <div style={{ marginBottom: 8 }}>Загрузка ёмкости</div>
                <Progress
                  type="dashboard"
                  percent={capacityPercent}
                  format={() => `${formatHours(result.total_planned_hours)} / ${formatHours(result.total_capacity_hours)} ч`}
                  status={capacityPercent > 90 ? 'exception' : 'normal'}
                  size={160}
                />
              </div>
              <div>
                <p>Включено задач: <strong>{result.included_count}</strong></p>
                <p>Пропущено: <strong>{result.skipped_count}</strong></p>
                <p>Остаток ёмкости: <strong>{formatHours(result.leftover_capacity_hours)} ч</strong></p>
              </div>
            </Space>

            <Table<AllocationResponse>
              dataSource={result.allocations}
              rowKey="backlog_item_id"
              pagination={false}
              size="small"
              columns={[
                { title: '#', dataIndex: 'priority', width: 60, render: (v: number | null) => v ?? '—' },
                { title: 'Задача', dataIndex: 'title' },
                { title: 'Оценка (ч)', dataIndex: 'estimate_hours', render: formatHours },
                { title: 'Запланировано (ч)', dataIndex: 'planned_hours', render: formatHours },
                {
                  title: 'Статус', dataIndex: 'included',
                  render: (v: boolean) => v ? <Tag color="green">Включена</Tag> : <Tag color="red">Пропущена</Tag>,
                },
                { title: 'Причина', dataIndex: 'reason' },
              ]}
              rowClassName={(r) => r.included ? '' : 'ant-table-row-disabled'}
            />
          </Space>
        </Card>
      )}
    </Space>
  );
}
