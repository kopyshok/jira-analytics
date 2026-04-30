import { useState } from 'react';
import { Card, Spin, Empty, Tooltip, Modal, InputNumber, Form } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import type {
  DashboardNormWorkResponse,
  NormWorkRoleGroup,
  NormWorkEmployee,
  NormWorkTypeBreakdown,
} from '../../types/api';

interface Thresholds { warnAbove: number; underBelow: number; }
const DEFAULT_THRESHOLDS: Thresholds = { warnAbove: 110, underBelow: 70 };

function statusColor(pct: number, t: Thresholds): string {
  if (pct > t.warnAbove) return '#ff4d4f';
  if (pct >= t.underBelow) return '#52c41a';
  return '#faad14';
}

function BulletBar({ plan, fact, color }: { plan: number; fact: number; color: string }) {
  const targetPct = 66;
  const fillW = plan > 0 ? Math.min(targetPct, (fact / plan) * targetPct) : 0;
  const overrunW = plan > 0 && fact > plan ? Math.min(100 - targetPct, ((fact - plan) / plan) * targetPct) : 0;
  return (
    <div style={{ position: 'relative', height: 14, background: '#1c3358', borderRadius: 7 }}>
      <div style={{
        position: 'absolute', top: 0, left: 0, height: '100%',
        width: `${fillW}%`, background: color, borderRadius: 7,
      }} />
      {overrunW > 0 && (
        <div style={{
          position: 'absolute', top: 0, left: `${targetPct}%`,
          height: '100%', width: `${overrunW}%`,
          background: '#ff4d4f', borderRadius: '0 7px 7px 0',
        }} />
      )}
      <div style={{
        position: 'absolute', top: -3, bottom: -3, left: `${targetPct}%`,
        width: 2, background: '#fff',
      }} />
    </div>
  );
}

function WorkTypeRow({ wt, t }: { wt: NormWorkTypeBreakdown; t: Thresholds }) {
  const color = statusColor(wt.pct, t);
  const fillW = wt.plan_hours > 0 ? Math.min(100, (wt.fact_hours / wt.plan_hours) * 100) : 0;
  return (
    <div style={{
      display: 'grid', gridTemplateColumns: '1fr auto 60px',
      gap: 8, alignItems: 'center', padding: '3px 0',
    }}>
      <span style={{ fontSize: 12, color: '#a4b8d8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {wt.label}
      </span>
      <div style={{ width: 50, height: 5, background: '#1c3358', borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${fillW}%`, background: color }} />
      </div>
      <span style={{ fontSize: 11, color: '#7e94b8', textAlign: 'right' }}>
        {Math.round(wt.fact_hours)}/{Math.round(wt.plan_hours)}
      </span>
    </div>
  );
}

function EmployeeBlock({ emp, role, t }: { emp: NormWorkEmployee; role: NormWorkRoleGroup; t: Thresholds }) {
  const color = statusColor(emp.pct, t);
  return (
    <div style={{ paddingBottom: 12, borderBottom: '1px solid rgba(28,51,88,.5)', marginBottom: 12 }}>
      <div style={{
        display: 'grid', gridTemplateColumns: '28px 1fr auto',
        gap: 8, alignItems: 'center', marginBottom: 8,
      }}>
        <div style={{
          width: 24, height: 24, borderRadius: '50%', background: role.role_color,
          color: '#fff', fontSize: 11, fontWeight: 700,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>{emp.initials}</div>
        <div style={{ fontSize: 14, color: '#e6edf7', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {emp.name}
        </div>
        <div style={{ fontSize: 14, fontWeight: 700, color }}>
          {Math.round(emp.pct)}%
        </div>
      </div>
      <BulletBar plan={emp.plan_hours} fact={emp.fact_hours} color={color} />
      <div style={{ fontSize: 12, color: '#7e94b8', marginTop: 4 }}>
        факт {Math.round(emp.fact_hours)} ч · план {Math.round(emp.plan_hours)} ч
      </div>
      <div style={{ marginTop: 8, marginLeft: 12 }}>
        {emp.work_types.map((wt) => (
          <WorkTypeRow key={wt.work_type_id} wt={wt} t={t} />
        ))}
      </div>
    </div>
  );
}

function RoleColumn({ role, t }: { role: NormWorkRoleGroup; t: Thresholds }) {
  return (
    <div style={{ background: '#0a1d3a', borderRadius: 8, overflow: 'hidden' }}>
      <div style={{ padding: 12, borderBottom: `2px solid ${role.role_color}` }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ width: 10, height: 10, borderRadius: '50%', background: role.role_color }} />
          <span style={{ fontSize: 16, fontWeight: 600, color: '#e6edf7' }}>{role.role_label}</span>
          <span style={{ fontSize: 13, color: '#7e94b8' }}>{role.employees_count} чел.</span>
        </div>
        <div style={{ fontSize: 13, color: '#7e94b8', marginTop: 4 }}>
          Σ план <b style={{ color: '#fff' }}>{Math.round(role.total_plan)} ч</b>
          {' · '}Σ факт <b style={{ color: '#fff' }}>{Math.round(role.total_fact)} ч</b>
          {' · '}средн. <b style={{ color: statusColor(role.total_pct, t) }}>{Math.round(role.total_pct)}%</b>
        </div>
      </div>
      <div style={{ padding: 12 }}>
        {role.employees.map((emp) => (
          <EmployeeBlock key={emp.employee_id} emp={emp} role={role} t={t} />
        ))}
        {role.employees.length === 0 && (
          <div style={{ color: '#7e94b8', fontSize: 13 }}>Нет сотрудников</div>
        )}
      </div>
    </div>
  );
}

interface Props {
  data: DashboardNormWorkResponse | undefined;
  loading: boolean;
}

export default function NormWorkWidget({ data, loading }: Props) {
  const [t, setT] = useState<Thresholds>(DEFAULT_THRESHOLDS);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm<Thresholds>();

  const gear = (
    <Tooltip title="Настройка порогов">
      <SettingOutlined
        style={{ cursor: 'pointer', color: '#7e94b8', fontSize: 16 }}
        onClick={() => { form.setFieldsValue(t); setModalOpen(true); }}
      />
    </Tooltip>
  );

  const title = (
    <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', gap: 16 }}>
      <span style={{ fontSize: 15, fontWeight: 600, color: '#e6edf7' }}>Нормированные работы</span>
      {data && !loading && (
        <span style={{ fontSize: 14, color: '#7e94b8' }}>
          Σ план <b style={{ color: '#fff' }}>{Math.round(data.total_plan)} ч</b>
          {' · '}Σ факт <b style={{ color: '#fff' }}>{Math.round(data.total_fact)} ч</b>
          {' · '}загрузка <b style={{ color: statusColor(data.total_pct, t) }}>{Math.round(data.total_pct)}%</b>
        </span>
      )}
      {gear}
    </span>
  );

  if (loading) return <Card title="Нормированные работы"><Spin /></Card>;
  if (!data?.roles.length) return <Card title={title}><Empty description="Нет данных" /></Card>;

  return (
    <>
      <Card title={title}>
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
          gap: 16,
          alignItems: 'flex-start',
        }}>
          {data.roles.map((r) => <RoleColumn key={r.role_code} role={r} t={t} />)}
        </div>
      </Card>

      <Modal
        title="Настройка порогов загрузки"
        open={modalOpen}
        onOk={() => form.validateFields().then((v) => { setT(v); setModalOpen(false); })}
        onCancel={() => setModalOpen(false)}
        okText="Применить"
        cancelText="Отмена"
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item label="Перегруз — выше, % (красный)" name="warnAbove" rules={[{ required: true, type: 'number', min: 1, max: 500 }]}>
            <InputNumber style={{ width: '100%' }} min={1} max={500} addonAfter="%" />
          </Form.Item>
          <Form.Item label="Недозагрузка — ниже, % (жёлтый)" name="underBelow" rules={[{ required: true, type: 'number', min: 1, max: 500 }]}>
            <InputNumber style={{ width: '100%' }} min={1} max={500} addonAfter="%" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
