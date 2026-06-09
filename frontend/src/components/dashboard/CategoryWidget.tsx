import { useState } from 'react';
import { Card, Spin, Empty, Popover, Button, InputNumber, Space } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router';
import { DARK_THEME } from '../../utils/constants';
import type { DashboardCategoriesResponse, CategoryMetaItem, EmployeeWorklogActivity } from '../../types/api';

const STORAGE_KEY = 'dashboard.categories.activityThresholds';

interface Thresholds {
  greenMax: number;   // ≤ greenMax дней — зелёный
  yellowMax: number;  // ≤ yellowMax дней — жёлтый, иначе красный
}

const DEFAULT_THRESHOLDS: Thresholds = { greenMax: 3, yellowMax: 5 };

function loadThresholds(): Thresholds {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_THRESHOLDS;
    const parsed = JSON.parse(raw) as Partial<Thresholds>;
    const greenMax = Number.isFinite(parsed.greenMax) ? Math.max(0, Math.floor(parsed.greenMax!)) : DEFAULT_THRESHOLDS.greenMax;
    const yellowMaxRaw = Number.isFinite(parsed.yellowMax) ? Math.max(0, Math.floor(parsed.yellowMax!)) : DEFAULT_THRESHOLDS.yellowMax;
    const yellowMax = Math.max(greenMax, yellowMaxRaw);
    return { greenMax, yellowMax };
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

function formatAgo(days: number | null): string {
  if (days == null) return 'нет ворклогов';
  if (days <= 0) return 'сегодня';
  if (days === 1) return '1 день назад';
  const last2 = days % 100;
  const last1 = days % 10;
  if (last2 >= 11 && last2 <= 14) return `${days} дней назад`;
  if (last1 >= 2 && last1 <= 4) return `${days} дня назад`;
  if (last1 === 1) return `${days} день назад`;
  return `${days} дней назад`;
}

function activityColor(days: number | null, t: Thresholds): string {
  if (days == null) return DARK_THEME.textMuted;
  if (days <= t.greenMax) return '#67d68d';
  if (days <= t.yellowMax) return '#faad14';
  return '#ff4d4f';
}

function ThresholdsPopover({ value, onChange }: { value: Thresholds; onChange: (t: Thresholds) => void }) {
  const setGreen = (v: number | null) => {
    const greenMax = Math.max(0, Math.floor(v ?? 0));
    const yellowMax = Math.max(greenMax, value.yellowMax);
    onChange({ greenMax, yellowMax });
  };
  const setYellow = (v: number | null) => {
    const yellowMax = Math.max(value.greenMax, Math.floor(v ?? 0));
    onChange({ greenMax: value.greenMax, yellowMax });
  };

  const content = (
    <Space orientation="vertical" size={12} style={{ minWidth: 240 }}>
      <div style={{ fontSize: 12, color: DARK_THEME.textMuted }}>
        До скольки дней без ворклога считать «нормой» (зелёный) и «предупреждением» (жёлтый). Всё что выше — красный.
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ width: 12, height: 12, borderRadius: '50%', background: '#67d68d' }} />
        <span style={{ flex: 1, fontSize: 13 }}>Зелёный — до</span>
        <InputNumber min={0} max={365} value={value.greenMax} onChange={setGreen} style={{ width: 80 }} suffix="д" />
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ width: 12, height: 12, borderRadius: '50%', background: '#faad14' }} />
        <span style={{ flex: 1, fontSize: 13 }}>Жёлтый — до</span>
        <InputNumber min={value.greenMax} max={365} value={value.yellowMax} onChange={setYellow} style={{ width: 80 }} suffix="д" />
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ width: 12, height: 12, borderRadius: '50%', background: '#ff4d4f' }} />
        <span style={{ flex: 1, fontSize: 13, color: DARK_THEME.textMuted }}>Красный — больше {value.yellowMax} д</span>
      </div>
      <Button size="small" onClick={() => onChange(DEFAULT_THRESHOLDS)}>Сбросить</Button>
    </Space>
  );

  return (
    <Popover content={content} title="Пороги активности" trigger="click" placement="bottomRight">
      <Button type="text" icon={<SettingOutlined />} aria-label="Пороги активности" />
    </Popover>
  );
}

function EmployeesActivity({ items, thresholds }: { items: EmployeeWorklogActivity[]; thresholds: Thresholds }) {
  const navigate = useNavigate();
  if (!items.length) return null;
  return (
    <div style={{ marginTop: 16 }}>
      <div style={{
        fontSize: 12,
        color: DARK_THEME.textMuted,
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        marginBottom: 10,
      }}>
        Последний ворклог сотрудника
      </div>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
        gap: 8,
      }}>
        {items.map((emp) => {
          const color = emp.is_absent ? DARK_THEME.textMuted : activityColor(emp.days_since_last, thresholds);
          const tooltip = [
            emp.is_absent && emp.absence_label ? `Сейчас: ${emp.absence_label}` : null,
            emp.last_worklog_at
              ? `Последний ворклог: ${new Date(emp.last_worklog_at).toLocaleString('ru-RU')}`
              : 'Нет ворклогов',
          ].filter(Boolean).join('\n');
          const openEmp = () => navigate(`/analytics?employee=${emp.employee_id}`);
          return (
            <div
              key={emp.employee_id}
              role="button"
              tabIndex={0}
              title={tooltip}
              onClick={openEmp}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openEmp(); } }}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 10,
                background: DARK_THEME.cardBg,
                border: `1px solid ${DARK_THEME.darkRows}`,
                borderRadius: 8,
                padding: '8px 12px',
                opacity: emp.is_absent ? 0.75 : 1,
                cursor: 'pointer',
              }}
            >
              <div style={{
                width: 28, height: 28, borderRadius: '50%',
                background: DARK_THEME.darkRows, color: 'var(--text-muted, #a4b8d8)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 11, fontWeight: 700, flexShrink: 0,
              }}>{emp.initials}</div>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 6,
                  color: 'var(--text, #e6edf7)', fontSize: 13,
                }}>
                  <span style={{
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                    flex: '0 1 auto', minWidth: 0,
                  }}>{emp.name}</span>
                  {emp.is_absent && (
                    <span style={{
                      background: '#a78bfa22',
                      color: '#a78bfa',
                      fontSize: 10,
                      fontWeight: 700,
                      padding: '1px 6px',
                      borderRadius: 4,
                      flexShrink: 0,
                      textTransform: 'uppercase',
                      letterSpacing: '0.04em',
                    }}>
                      {emp.absence_label || 'отсутствует'}
                    </span>
                  )}
                </div>
                <div style={{ color, fontSize: 12, fontWeight: 600 }}>
                  {formatAgo(emp.days_since_last)}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function HeatmapGrid({ items }: { items: CategoryMetaItem[] }) {
  const navigate = useNavigate();
  if (!items.length) return <Empty description="Нет данных" />;

  const visible = items.slice(0, 10);
  const overflow = items.length > 10 ? items.slice(10) : [];

  const cells: (CategoryMetaItem | { _overflow: true; count: number; hours: number })[] = [...visible];
  if (overflow.length) {
    cells.push({
      _overflow: true,
      count: overflow.length,
      hours: overflow.reduce((s, i) => s + i.hours, 0),
    });
  }

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(5, 1fr)',
        gridAutoRows: 'minmax(140px, 1fr)',
        gap: 6,
        width: '100%',
      }}
    >
      {cells.map((c, idx) => {
        if ('_overflow' in c) {
          return (
            <div
              key={`overflow-${idx}`}
              style={{
                background: '#1c335833',
                border: '1px solid #1c335866',
                borderRadius: 8,
                padding: 12,
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ fontSize: 12, color: 'var(--text-muted, #a4b8d8)' }}>+ ещё {c.count}</div>
              <div style={{ fontSize: 24, fontWeight: 700, color: DARK_THEME.textPrimary }}>{Math.round(c.hours)} ч</div>
            </div>
          );
        }
        const item = c;
        const openCategory = () => navigate(`/analytics?category=${encodeURIComponent(item.key)}`);
        return (
          <div
            key={item.key}
            role="button"
            tabIndex={0}
            title={`${item.label}: ${Math.round(item.hours)} ч (${item.pct.toFixed(1)}%)`}
            onClick={openCategory}
            onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openCategory(); } }}
            style={{
              background: `${item.color}33`,
              border: `1px solid ${item.color}66`,
              borderRadius: 8,
              padding: 12,
              position: 'relative',
              display: 'flex',
              flexDirection: 'column',
              justifyContent: 'space-between',
              overflow: 'hidden',
              cursor: 'pointer',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
              <div style={{
                fontSize: 12,
                color: 'var(--text-muted, #a4b8d8)',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                flex: 1,
              }}>
                {item.label}
              </div>
              <span style={{
                fontSize: 10,
                fontWeight: 700,
                background: item.color,
                color: DARK_THEME.textPrimary,
                padding: '2px 6px',
                borderRadius: 6,
                flexShrink: 0,
              }}>
                {item.pct.toFixed(0)}%
              </span>
            </div>
            <div style={{ fontSize: 24, fontWeight: 700, color: DARK_THEME.textPrimary }}>{Math.round(item.hours)} ч</div>
            <div style={{ fontSize: 10, color: DARK_THEME.textMuted }}>
              {item.worklog_count} wl · {item.issue_count} зад · {item.employee_count} чел
            </div>
            <div style={{
              position: 'absolute',
              bottom: 0,
              left: 0,
              height: 3,
              width: `${Math.min(100, item.pct)}%`,
              background: item.color,
            }} />
          </div>
        );
      })}
    </div>
  );
}

function SummaryStrip({ items }: { items: CategoryMetaItem[] }) {
  const totalHours = items.reduce((s, i) => s + i.hours, 0);
  const totalWl = items.reduce((s, i) => s + i.worklog_count, 0);
  const totalIssues = items.reduce((s, i) => s + i.issue_count, 0);
  const avgMin = totalWl > 0
    ? items.reduce((s, i) => s + i.avg_worklog_minutes * i.worklog_count, 0) / totalWl
    : 0;
  return (
    <div style={{
      display: 'flex',
      flexWrap: 'wrap',
      gap: 16,
      marginTop: 12,
      fontSize: 12,
      color: DARK_THEME.textMuted,
    }}>
      <span>Σ часов: <b style={{ color: DARK_THEME.textPrimary }}>{Math.round(totalHours)}</b></span>
      <span>Σ ворклогов: <b style={{ color: DARK_THEME.textPrimary }}>{totalWl}</b></span>
      <span>Σ задач: <b style={{ color: DARK_THEME.textPrimary }}>{totalIssues}</b></span>
      <span>{items.length} категорий</span>
      <span>средн. <b style={{ color: DARK_THEME.textPrimary }}>{avgMin.toFixed(0)}</b> мин/wl</span>
    </div>
  );
}

function MetaTable({ items }: { items: CategoryMetaItem[] }) {
  const totalHours = items.reduce((s, i) => s + i.hours, 0);
  const totalWl = items.reduce((s, i) => s + i.worklog_count, 0);
  const totalIssues = items.reduce((s, i) => s + i.issue_count, 0);

  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr style={{ color: DARK_THEME.textMuted, fontSize: 10, textTransform: 'uppercase' }}>
            {['Категория', 'Часы', 'Вркл.', 'Задач', 'Сотр.', 'Ср.мин', '%'].map((h) => (
              <th key={h} style={{ textAlign: h === 'Категория' ? 'left' : 'right', padding: '4px 8px', borderBottom: `1px solid ${DARK_THEME.darkRows}` }}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {items.map((item) => (
            <tr key={item.key} style={{ borderBottom: '1px solid rgba(28,51,88,.3)' }}>
              <td style={{ padding: '5px 8px' }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  <span style={{ width: 8, height: 8, borderRadius: 2, background: item.color, flexShrink: 0, display: 'inline-block' }} />
                  <span style={{ color: 'var(--text, #e6edf7)' }}>{item.label}</span>
                </span>
              </td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: DARK_THEME.textPrimary, fontWeight: 600 }}>{Math.round(item.hours)}</td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: 'var(--text-muted, #a4b8d8)' }}>{item.worklog_count}</td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: 'var(--text-muted, #a4b8d8)' }}>{item.issue_count}</td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: 'var(--text-muted, #a4b8d8)' }}>{item.employee_count}</td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: 'var(--text-muted, #a4b8d8)' }}>{item.avg_worklog_minutes.toFixed(0)}</td>
              <td style={{ textAlign: 'right', padding: '5px 8px', color: DARK_THEME.textMuted }}>{item.pct.toFixed(1)}%</td>
            </tr>
          ))}
          <tr style={{ borderTop: `2px solid ${DARK_THEME.darkRows}`, fontWeight: 600, color: DARK_THEME.textPrimary, fontSize: 11 }}>
            <td style={{ padding: '5px 8px' }}>Итого</td>
            <td style={{ textAlign: 'right', padding: '5px 8px' }}>{Math.round(totalHours)}</td>
            <td style={{ textAlign: 'right', padding: '5px 8px', color: 'var(--text-muted, #a4b8d8)' }}>{totalWl}</td>
            <td style={{ textAlign: 'right', padding: '5px 8px', color: 'var(--text-muted, #a4b8d8)' }}>{totalIssues}</td>
            <td colSpan={3} />
          </tr>
        </tbody>
      </table>
    </div>
  );
}

interface Props {
  data: DashboardCategoriesResponse | undefined;
  loading: boolean;
}

export default function CategoryWidget({ data, loading }: Props) {
  const [thresholds, setThresholdsState] = useState<Thresholds>(() => loadThresholds());
  const setThresholds = (t: Thresholds) => {
    setThresholdsState(t);
    saveThresholds(t);
  };
  const extra = <ThresholdsPopover value={thresholds} onChange={setThresholds} />;

  if (loading) return <Card title="Ворклоги по категориям" extra={extra}><Spin /></Card>;
  if (!data || (!data.items.length && !data.employees.length)) {
    return <Card title="Ворклоги по категориям" extra={extra}><Empty description="Нет данных" /></Card>;
  }

  return (
    <Card title="Ворклоги по категориям задач" extra={extra}>
      {data.items.length > 0 && (
        <div style={{ display: 'grid', gridTemplateColumns: '60% 40%', gap: 16 }}>
          <div>
            <HeatmapGrid items={data.items} />
            <SummaryStrip items={data.items} />
          </div>
          <MetaTable items={data.items} />
        </div>
      )}
      <EmployeesActivity items={data.employees} thresholds={thresholds} />
    </Card>
  );
}
