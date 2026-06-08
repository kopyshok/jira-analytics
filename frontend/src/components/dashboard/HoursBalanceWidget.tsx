import { useState, useMemo } from 'react';
import { Card, Spin, Empty, Select, Modal, InputNumber, Form, Button, Tooltip, message } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import { DARK_THEME } from '../../utils/constants';
import { useHoursBalance } from '../../hooks/useHoursBalance';
import { useAppearanceSettings } from '../../contexts/AppearanceContext';
import { useUpdateAppearance } from '../../api/appearance';
import type { HoursBalanceEmployee } from '../../types/api';
import HoursBalanceModal from './HoursBalanceModal';

type SortKey =
  | 'abs_desc'
  | 'balance_desc'
  | 'balance_asc'
  | 'name'
  | 'role';

function balanceColor(b: number): string {
  if (b > 1) return '#ff4d4f'; // переработка — красный
  if (b < -1) return '#faad14'; // недоработка — оранжевый
  return '#8aa0c0';
}

function Sparkline({ data, color }: { data: number[]; color: string }) {
  if (!data.length) return null;
  const w = 180;
  const h = 40;
  const min = Math.min(...data, 0);
  const max = Math.max(...data, 0);
  const span = Math.max(max - min, 1);
  const stepX = data.length > 1 ? w / (data.length - 1) : 0;
  const points = data
    .map((v, i) => `${i * stepX},${h - ((v - min) / span) * h}`)
    .join(' ');
  const zeroY = h - ((0 - min) / span) * h;
  return (
    <svg width={w} height={h} style={{ display: 'block' }}>
      <line
        x1={0}
        y1={zeroY}
        x2={w}
        y2={zeroY}
        stroke={DARK_THEME.textMuted}
        strokeDasharray="2 3"
        strokeOpacity={0.4}
      />
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={2}
      />
    </svg>
  );
}

function EmployeeCard({
  emp,
  onClick,
}: {
  emp: HoursBalanceEmployee;
  onClick: () => void;
}) {
  const color = balanceColor(emp.balance_hours);
  const sign = emp.balance_hours > 0 ? '+' : '';
  return (
    <div
      onClick={onClick}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') onClick(); }}
      style={{
        background: DARK_THEME.darkAccent,
        border: `1px solid ${DARK_THEME.border}`,
        borderRadius: 10,
        padding: 16,
        cursor: 'pointer',
        transition: 'transform .12s, border-color .12s',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = DARK_THEME.cyanPrimary;
        e.currentTarget.style.transform = 'scale(1.015)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = DARK_THEME.border;
        e.currentTarget.style.transform = 'scale(1)';
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <div style={{
          width: 40, height: 40, borderRadius: '50%',
          background: 'linear-gradient(135deg, #00c9c8, #4a6cf7)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#fff', fontWeight: 700, fontSize: 14,
        }}>{emp.initials}</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            color: DARK_THEME.textPrimary, fontSize: 15, fontWeight: 600,
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>{emp.full_name}</div>
          <div style={{ color: DARK_THEME.textMuted, fontSize: 12 }}>
            {emp.role_label ?? '—'}
          </div>
        </div>
        <div style={{ fontSize: 28, fontWeight: 700, color }}>
          {sign}{Math.round(emp.balance_hours)}ч
        </div>
      </div>
      <Sparkline data={emp.sparkline} color={color} />
      <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
        <span style={{
          fontSize: 11, padding: '2px 8px', borderRadius: 4,
          background: 'rgba(255,77,79,.12)', color: '#ff7875',
        }}>
          Переработок: {emp.overtime_days} дн · +{Math.round(emp.overtime_hours)}ч
        </span>
        <span style={{
          fontSize: 11, padding: '2px 8px', borderRadius: 4,
          background: 'rgba(110,122,153,.18)', color: '#a4b8d8',
        }}>
          Отгулов: {emp.skip_days} дн · {Math.round(emp.skip_hours)}ч
        </span>
      </div>
      <div style={{
        fontSize: 11, color: DARK_THEME.textMuted,
        fontStyle: 'italic', marginTop: 6,
      }}>Клик — детальный календарь</div>
    </div>
  );
}

function LagSettingsModal({
  open,
  current,
  onClose,
}: {
  open: boolean;
  current: number;
  onClose: () => void;
}) {
  const [form] = Form.useForm<{ lag_days: number }>();
  const appearance = useAppearanceSettings();
  const updater = useUpdateAppearance();
  const handleSave = async () => {
    const values = await form.validateFields();
    try {
      await updater.mutateAsync({ ...appearance, hours_balance_lag_days: values.lag_days });
      message.success('Настройка сохранена');
      onClose();
    } catch {
      message.error('Не удалось сохранить настройку');
    }
  };
  return (
    <Modal
      open={open}
      onCancel={onClose}
      onOk={handleSave}
      confirmLoading={updater.isPending}
      title="Лаг рабочих дней"
      okText="Сохранить"
      cancelText="Отмена"
    >
      <p style={{ color: DARK_THEME.textMuted, fontSize: 13, marginBottom: 16 }}>
        Сдвиг правой границы окна назад на N рабочих дней. Учитывает что сотрудники
        списывают часы с задержкой. По умолчанию — 2 рабочих дня.
      </p>
      <Form form={form} layout="vertical" initialValues={{ lag_days: current }}>
        <Form.Item
          label="Лаг (рабочих дней)"
          name="lag_days"
          rules={[{ required: true, type: 'number', min: 0, max: 10 }]}
        >
          <InputNumber min={0} max={10} style={{ width: 120 }} />
        </Form.Item>
      </Form>
    </Modal>
  );
}

export default function HoursBalanceWidget() {
  const { data, isLoading } = useHoursBalance();
  const appearance = useAppearanceSettings();
  const [sortKey, setSortKey] = useState<SortKey>('abs_desc');
  const [openId, setOpenId] = useState<string | null>(null);
  const [lagModalOpen, setLagModalOpen] = useState(false);

  const sorted = useMemo(() => {
    if (!data) return [];
    const arr = [...data.employees];
    switch (sortKey) {
      case 'abs_desc':
        arr.sort((a, b) => Math.abs(b.balance_hours) - Math.abs(a.balance_hours));
        break;
      case 'balance_desc':
        arr.sort((a, b) => b.balance_hours - a.balance_hours);
        break;
      case 'balance_asc':
        arr.sort((a, b) => a.balance_hours - b.balance_hours);
        break;
      case 'name':
        arr.sort((a, b) => a.full_name.localeCompare(b.full_name, 'ru'));
        break;
      case 'role':
        arr.sort((a, b) => {
          const r = (a.role_label ?? '').localeCompare(b.role_label ?? '', 'ru');
          return r !== 0 ? r : a.full_name.localeCompare(b.full_name, 'ru');
        });
        break;
    }
    return arr;
  }, [data, sortKey]);

  if (isLoading) {
    return (
      <Card style={{ background: DARK_THEME.cardBg, border: `1px solid ${DARK_THEME.border}` }}>
        <Spin />
      </Card>
    );
  }
  if (!data || data.employees.length === 0) {
    return (
      <Card
        title={<span style={{ color: DARK_THEME.textPrimary }}>Баланс часов команды</span>}
        style={{ background: DARK_THEME.cardBg, border: `1px solid ${DARK_THEME.border}` }}
      >
        <Empty description="Нет активных сотрудников в выбранных командах" />
      </Card>
    );
  }

  const t = data.team_summary;
  return (
    <Card
      title={
        <div>
          <div style={{ color: DARK_THEME.textPrimary, fontSize: 16 }}>
            Баланс часов команды
          </div>
          <div style={{ color: DARK_THEME.textMuted, fontSize: 12, fontWeight: 400, marginTop: 2 }}>
            С {data.period.from.split('-').reverse().join('.')} по {data.period.to.split('-').reverse().join('.')} · {data.period.working_days} рабочих дней · норма с учётом отпусков
            {appearance.hours_balance_lag_days > 0 && (
              <> · лаг {appearance.hours_balance_lag_days} раб. дн.</>
            )}
          </div>
        </div>
      }
      extra={
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <Select
            value={sortKey}
            onChange={(v) => setSortKey(v as SortKey)}
            size="small"
            style={{ width: 220 }}
            options={[
              { value: 'abs_desc', label: 'По отклонению' },
              { value: 'balance_desc', label: 'Больше переработали' },
              { value: 'balance_asc', label: 'Больше недоработали' },
              { value: 'name', label: 'По имени' },
              { value: 'role', label: 'По роли' },
            ]}
          />
          <Tooltip title="Настроить лаг рабочих дней">
            <Button
              type="text"
              size="small"
              icon={<SettingOutlined />}
              onClick={() => setLagModalOpen(true)}
              style={{ color: DARK_THEME.textMuted }}
            />
          </Tooltip>
        </div>
      }
      style={{ background: DARK_THEME.cardBg, border: `1px solid ${DARK_THEME.border}` }}
    >
      <div style={{
        background: DARK_THEME.darkAccent, borderRadius: 6, padding: '8px 12px',
        marginBottom: 16, fontSize: 13, color: DARK_THEME.textMuted,
      }}>
        Команда: {t.employees_count} чел ·
        переработки <span style={{ color: '#ff7875' }}>+{Math.round(t.overtime_hours)}ч</span> ·
        автоотгулы <span style={{ color: '#a4b8d8' }}>{Math.round(t.skip_hours)}ч</span> ·
        нетто <span style={{ color: balanceColor(t.net_balance), fontWeight: 600 }}>
          {t.net_balance > 0 ? '+' : ''}{Math.round(t.net_balance)}ч
        </span>
      </div>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
        gap: 12,
      }}>
        {sorted.map((emp) => (
          <EmployeeCard
            key={emp.id}
            emp={emp}
            onClick={() => setOpenId(emp.id)}
          />
        ))}
      </div>
      <div style={{
        marginTop: 12, textAlign: 'center', fontSize: 11,
        color: DARK_THEME.textMuted, fontStyle: 'italic',
      }}>
        Работа в выходные, праздники, отпуск или больничный засчитывается переработкой.
      </div>
      <HoursBalanceModal
        employeeId={openId}
        onClose={() => setOpenId(null)}
      />
      <LagSettingsModal
        open={lagModalOpen}
        current={appearance.hours_balance_lag_days}
        onClose={() => setLagModalOpen(false)}
      />
    </Card>
  );
}
