import { useState, type KeyboardEvent } from 'react';
import { Card, Spin, Empty, Tooltip, Modal, InputNumber, Form, Button } from 'antd';
import { SettingOutlined, BarChartOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router';
import { useGlobalPeriod } from '../../hooks/useGlobalPeriod';
import { useGlobalTeamFilter } from '../../hooks/useGlobalTeamFilter';
import { DARK_THEME } from '../../utils/constants';
import type {
  DashboardNormWorkResponse,
  NormWorkRoleGroup,
  NormWorkEmployee,
  NormWorkTypeBreakdown,
} from '../../types/api';

interface Thresholds { warnAbove: number; underBelow: number; }
const DEFAULT_THRESHOLDS: Thresholds = { warnAbove: 110, underBelow: 70 };
const STORAGE_KEY = 'dashboard.normWork.thresholds';

function loadThresholds(): Thresholds {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_THRESHOLDS;
    const parsed = JSON.parse(raw) as Partial<Thresholds>;
    const warnAbove = Number.isFinite(parsed.warnAbove) ? Math.max(1, Math.min(500, Math.floor(parsed.warnAbove!))) : DEFAULT_THRESHOLDS.warnAbove;
    const underBelow = Number.isFinite(parsed.underBelow) ? Math.max(1, Math.min(500, Math.floor(parsed.underBelow!))) : DEFAULT_THRESHOLDS.underBelow;
    return { warnAbove, underBelow };
  } catch {
    return DEFAULT_THRESHOLDS;
  }
}

function saveThresholds(t: Thresholds) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(t));
  } catch {
    // ignore
  }
}

function statusColor(pct: number, t: Thresholds): string {
  // pct > warnAbove → перегруз (красный); underBelow ≤ pct ≤ warnAbove → норма (жёлтый);
  // pct < underBelow → недогрузка (зелёный, есть запас).
  if (pct > t.warnAbove) return '#ff4d4f';
  if (pct >= t.underBelow) return '#faad14';
  return '#52c41a';
}

function BulletBar({ plan, fact, color }: { plan: number; fact: number; color: string }) {
  const targetPct = 66;
  const fillW = plan > 0 ? Math.min(targetPct, (fact / plan) * targetPct) : 0;
  const overrunW = plan > 0 && fact > plan ? Math.min(100 - targetPct, ((fact - plan) / plan) * targetPct) : 0;
  return (
    <div style={{ position: 'relative', height: 14, background: DARK_THEME.darkRows, borderRadius: 7 }}>
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
        width: 2, background: DARK_THEME.textPrimary,
      }} />
    </div>
  );
}

function WorkTypeRow({
  wt, t, onOpen, onOpenThematic,
}: {
  wt: NormWorkTypeBreakdown;
  t: Thresholds;
  onOpen?: () => void;
  onOpenThematic?: () => void;
}) {
  // План 0 + факт > 0 = всегда перегруз (например, чужие/прочие задачи без выделенного плана)
  const overflowZeroPlan = wt.plan_hours === 0 && wt.fact_hours > 0;
  const color = overflowZeroPlan ? '#ff4d4f' : statusColor(wt.pct, t);
  const fillW = wt.plan_hours > 0
    ? Math.min(100, (wt.fact_hours / wt.plan_hours) * 100)
    : (overflowZeroPlan ? 100 : 0);
  const interactiveProps = onOpen
    ? {
        role: 'button' as const,
        tabIndex: 0,
        onClick: onOpen,
        onKeyDown: (e: KeyboardEvent) => {
          if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onOpen(); }
        },
      }
    : {};
  return (
    <div {...interactiveProps} style={{
      display: 'grid', gridTemplateColumns: '1fr auto 60px auto',
      gap: 8, alignItems: 'center', padding: '3px 0',
      cursor: onOpen ? 'pointer' : 'default',
    }}>
      <span style={{
        fontSize: 12,
        color: overflowZeroPlan ? '#ff4d4f' : '#a4b8d8',
        fontWeight: overflowZeroPlan ? 600 : 400,
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>
        {wt.label}
      </span>
      <div style={{ width: 50, height: 5, background: DARK_THEME.darkRows, borderRadius: 2, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${fillW}%`, background: color }} />
      </div>
      <span style={{
        fontSize: 11,
        color: overflowZeroPlan ? '#ff4d4f' : DARK_THEME.textMuted,
        fontWeight: overflowZeroPlan ? 600 : 400,
        textAlign: 'right',
      }}>
        {Math.round(wt.fact_hours)}/{Math.round(wt.plan_hours)}
      </span>
      {onOpenThematic ? (
        <Tooltip title="Тематический отчёт">
          <Button
            type="link"
            size="small"
            icon={<BarChartOutlined />}
            style={{ padding: 0, height: 'auto', color: DARK_THEME.cyanPrimary }}
            onClick={(e) => { e.stopPropagation(); onOpenThematic(); }}
          />
        </Tooltip>
      ) : (
        <span />
      )}
    </div>
  );
}

const FOREIGN_BADGE_MIN_HOURS = 8;
const FOREIGN_BADGE_MIN_PCT = 5;

function ForeignBadge({ hours, pct, compact = false }: { hours: number; pct: number; compact?: boolean }) {
  if (hours <= 0) return null;
  const label = `чужие ${Math.round(hours)} ч · ${Math.round(pct)}%`;
  return (
    <Tooltip title="Часы сотрудника на задачи чужой продуктовой команды (из общего факта)">
      <span style={{
        fontSize: compact ? 11 : 12,
        padding: compact ? '1px 6px' : '2px 8px',
        borderRadius: 4,
        background: 'rgba(255, 77, 79, 0.12)',
        color: '#ff7875',
        border: '1px solid rgba(255, 77, 79, 0.35)',
        whiteSpace: 'nowrap',
      }}>{label}</span>
    </Tooltip>
  );
}

function EmployeeBlock({ emp, role, t }: { emp: NormWorkEmployee; role: NormWorkRoleGroup; t: Thresholds }) {
  const navigate = useNavigate();
  const { period } = useGlobalPeriod();
  const { selectedTeams } = useGlobalTeamFilter();
  const color = statusColor(emp.pct, t);
  const showForeignBadge =
    emp.foreign_hours >= FOREIGN_BADGE_MIN_HOURS || emp.foreign_pct >= FOREIGN_BADGE_MIN_PCT;
  const openAnalytics = (extra: Record<string, string> = {}) => {
    const params = new URLSearchParams({ employee: emp.employee_id, ...extra });
    navigate(`/analytics?${params.toString()}`);
  };
  const openThematic = (wt: NormWorkTypeBreakdown) => {
    const params = new URLSearchParams({
      work_type_id: wt.work_type_id,
      year: String(period.year),
      quarter: String(period.quarter),
      ...(period.month != null ? { month: String(period.month) } : {}),
      ...(selectedTeams.length > 0 ? { teams: selectedTeams.join(',') } : {}),
    });
    navigate(`/analytics/work-type-report?${params.toString()}`);
  };
  const handleOpenAnalytics = () => openAnalytics();
  return (
    <div style={{ paddingBottom: 12, borderBottom: '1px solid rgba(28,51,88,.5)', marginBottom: 12 }}>
      <div
        role="button"
        tabIndex={0}
        onClick={handleOpenAnalytics}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleOpenAnalytics(); } }}
        style={{
          display: 'grid', gridTemplateColumns: '28px 1fr auto auto',
          gap: 8, alignItems: 'center', marginBottom: 8,
          cursor: 'pointer',
        }}>
        <div style={{
          width: 24, height: 24, borderRadius: '50%', background: role.role_color,
          color: DARK_THEME.textPrimary, fontSize: 11, fontWeight: 700,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>{emp.initials}</div>
        <div style={{ fontSize: 14, color: '#e6edf7', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {emp.name}
        </div>
        {showForeignBadge ? <ForeignBadge hours={emp.foreign_hours} pct={emp.foreign_pct} compact /> : <span />}
        <div style={{ fontSize: 14, fontWeight: 700, color }}>
          {Math.round(emp.pct)}%
        </div>
      </div>
      <BulletBar plan={emp.plan_hours} fact={emp.fact_hours} color={color} />
      <div style={{ fontSize: 12, color: DARK_THEME.textMuted, marginTop: 4 }}>
        факт {Math.round(emp.fact_hours)} ч · план {Math.round(emp.plan_hours)} ч
      </div>
      <div style={{ marginTop: 8, marginLeft: 12 }}>
        {emp.work_types.map((wt) => (
          <WorkTypeRow
            key={wt.work_type_id}
            wt={wt}
            t={t}
            onOpen={wt.work_type_code ? () => openAnalytics({ work_type: wt.work_type_code! }) : undefined}
            onOpenThematic={() => openThematic(wt)}
          />
        ))}
      </div>
    </div>
  );
}

function RoleColumn({ role, t }: { role: NormWorkRoleGroup; t: Thresholds }) {
  return (
    <div style={{ background: DARK_THEME.cardBg, borderRadius: 8, overflow: 'hidden' }}>
      <div style={{ padding: 12, borderBottom: `2px solid ${role.role_color}` }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ width: 10, height: 10, borderRadius: '50%', background: role.role_color }} />
          <span style={{ fontSize: 16, fontWeight: 600, color: '#e6edf7' }}>{role.role_label}</span>
          <span style={{ fontSize: 13, color: DARK_THEME.textMuted }}>{role.employees_count} чел.</span>
        </div>
        <div style={{ fontSize: 13, color: DARK_THEME.textMuted, marginTop: 4 }}>
          Σ план <b style={{ color: DARK_THEME.textPrimary }}>{Math.round(role.total_plan)} ч</b>
          {' · '}Σ факт <b style={{ color: DARK_THEME.textPrimary }}>{Math.round(role.total_fact)} ч</b>
          {' · '}средн. <b style={{ color: statusColor(role.total_pct, t) }}>{Math.round(role.total_pct)}%</b>
          {role.foreign_hours > 0 && (
            <>
              {' · '}
              <Tooltip title="Часы роли на задачи чужих продуктовых команд (из общего факта)">
                <span style={{ color: '#ff7875' }}>
                  чужие <b>{Math.round(role.foreign_hours)} ч</b> ({Math.round(role.foreign_pct)}%)
                </span>
              </Tooltip>
            </>
          )}
        </div>
      </div>
      <div style={{ padding: 12 }}>
        {role.employees.map((emp) => (
          <EmployeeBlock key={emp.employee_id} emp={emp} role={role} t={t} />
        ))}
        {role.employees.length === 0 && (
          <div style={{ color: DARK_THEME.textMuted, fontSize: 13 }}>Нет сотрудников</div>
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
  const [t, setT] = useState<Thresholds>(loadThresholds);
  const [modalOpen, setModalOpen] = useState(false);
  const [form] = Form.useForm<Thresholds>();

  const gear = (
    <Tooltip title="Настройка порогов">
      <SettingOutlined
        style={{ cursor: 'pointer', color: DARK_THEME.textMuted, fontSize: 16 }}
        onClick={() => { form.setFieldsValue(t); setModalOpen(true); }}
      />
    </Tooltip>
  );

  const title = (
    <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', gap: 16 }}>
      <span style={{ fontSize: 15, fontWeight: 600, color: '#e6edf7' }}>Нормированные работы</span>
      {data && !loading && (
        <span style={{ fontSize: 14, color: DARK_THEME.textMuted, display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <span>
            Σ план <b style={{ color: DARK_THEME.textPrimary }}>{Math.round(data.total_plan)} ч</b>
            {' · '}Σ факт <b style={{ color: DARK_THEME.textPrimary }}>{Math.round(data.total_fact)} ч</b>
            {' · '}загрузка <b style={{ color: statusColor(data.total_pct, t) }}>{Math.round(data.total_pct)}%</b>
          </span>
          {data.foreign_hours > 0 && (
            <ForeignBadge hours={data.foreign_hours} pct={data.foreign_pct} />
          )}
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
        onOk={() => form.validateFields().then((v) => { setT(v); saveThresholds(v); setModalOpen(false); })}
        onCancel={() => setModalOpen(false)}
        okText="Применить"
        cancelText="Отмена"
      >
        <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
          <Form.Item label="Перегруз — выше, % (красный)" name="warnAbove" rules={[{ required: true, type: 'number', min: 1, max: 500 }]}>
            <InputNumber style={{ width: '100%' }} min={1} max={500} suffix="%" />
          </Form.Item>
          <Form.Item label="Недозагрузка — ниже, % (зелёный)" name="underBelow" rules={[{ required: true, type: 'number', min: 1, max: 500 }]}>
            <InputNumber style={{ width: '100%' }} min={1} max={500} suffix="%" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
