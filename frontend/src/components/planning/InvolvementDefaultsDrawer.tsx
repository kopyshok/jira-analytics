import { useState } from 'react';
import {
  App, Button, Drawer, InputNumber, Popconfirm, Select, Space, Table,
} from 'antd';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import {
  useInvolvementDefaults,
  useCreateInvolvementDefault,
  useDeleteInvolvementDefault,
} from '../../hooks/useInvolvementDefaults';

const ROLE_LABELS: Record<string, string> = {
  analyst: 'Анализ',
  dev: 'Разработка',
  qa: 'Тестирование',
  opo: 'ОПЭ',
};
const ROLE_OPTIONS = Object.entries(ROLE_LABELS).map(([value, label]) => ({ value, label }));
const QUARTER_OPTIONS = [1, 2, 3, 4].map((q) => ({ value: q, label: `Q${q}` }));

export default function InvolvementDefaultsDrawer({
  open, onClose, team,
}: {
  open: boolean;
  onClose: () => void;
  team: string | null;
}) {
  const { notification } = App.useApp();
  const { data = [], isLoading } = useInvolvementDefaults(team);
  const create = useCreateInvolvementDefault();
  const del = useDeleteInvolvementDefault();

  const now = new Date();
  const [role, setRole] = useState('analyst');
  const [year, setYear] = useState<number>(now.getFullYear());
  const [quarter, setQuarter] = useState<number>(1);
  const [value, setValue] = useState<number | null>(0.8);

  const handleAdd = () => {
    if (!team || value == null) return;
    create.mutate(
      { team, role, effective_year: year, effective_quarter: quarter, involvement: value },
      {
        onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }),
      },
    );
  };

  const columns = [
    { title: 'Роль', dataIndex: 'role', render: (r: string) => ROLE_LABELS[r] ?? r },
    {
      title: 'Действует с',
      key: 'eff',
      render: (_: unknown, row: { effective_quarter: number; effective_year: number }) =>
        `Q${row.effective_quarter} ${row.effective_year}`,
    },
    { title: 'Вовлечённость', dataIndex: 'involvement' },
    {
      title: '',
      key: 'act',
      width: 48,
      render: (_: unknown, row: { id: string }) => (
        <Popconfirm title="Удалить?" onConfirm={() => del.mutate(row.id)}>
          <Button size="small" danger icon={<DeleteOutlined />} />
        </Popconfirm>
      ),
    },
  ];

  return (
    <Drawer
      open={open}
      onClose={onClose}
      styles={{ wrapper: { width: 560 } }}
      title={`Справочник вовлечённости${team ? ` · ${team}` : ''}`}
    >
      {!team ? (
        <div>Выберите команду сценария.</div>
      ) : (
        <Space orientation="vertical" size={16} style={{ width: '100%' }}>
          <Space wrap>
            <Select style={{ width: 150 }} value={role} onChange={setRole} options={ROLE_OPTIONS} />
            <Select style={{ width: 90 }} value={quarter} onChange={setQuarter} options={QUARTER_OPTIONS} />
            <InputNumber style={{ width: 100 }} value={year} onChange={(v) => setYear(v ?? year)} min={2000} max={2100} />
            <InputNumber style={{ width: 110 }} value={value} onChange={setValue} min={0} max={1} step={0.05} placeholder="0–1" />
            <Button type="primary" icon={<PlusOutlined />} loading={create.isPending} onClick={handleAdd}>
              Добавить
            </Button>
          </Space>
          <Table
            rowKey="id"
            size="small"
            loading={isLoading}
            dataSource={data}
            columns={columns}
            pagination={false}
          />
        </Space>
      )}
    </Drawer>
  );
}
