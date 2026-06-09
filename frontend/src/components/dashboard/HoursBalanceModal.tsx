import { Modal, Spin, Tooltip } from 'antd';
import { DARK_THEME } from '../../utils/constants';
import { useHoursBalanceDetail } from '../../hooks/useHoursBalance';
import type { HoursBalanceDailyEntry } from '../../types/api';

interface Props {
  employeeId: string | null;
  onClose: () => void;
}

const WEEKDAY_LABELS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

const MONTH_NAMES_RU = [
  'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
  'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь',
];

function balanceColor(b: number): string {
  if (b > 1) return '#ff4d4f';
  if (b < -1) return '#faad14';
  return '#8aa0c0';
}

// Часы в overlay ячейки: с 1 знаком после запятой если есть дробь, иначе целое.
// Сумма округлений ≠ округление суммы — поэтому overlay должен отражать точную величину.
function formatDelta(d: number): string {
  const rounded = Math.round(d * 10) / 10;
  return Number.isInteger(rounded) ? String(rounded) : rounded.toFixed(1);
}

function dayBg(kind: string): { bg: string; border: string; tone: string } {
  switch (kind) {
    case 'overtime':
      return { bg: '#3d1b1d', border: '#ff4d4f', tone: '#ff7875' };
    case 'skip':
      return { bg: '#2a2f42', border: '#6e7a99', tone: 'var(--text-muted, #a4b8d8)' };
    case 'norm':
      return { bg: '#1d3d22', border: '#52c41a', tone: '#52c41a' };
    case 'absence':
      return { bg: '#3b3155', border: '#6e5fb0', tone: '#b39ddb' };
    case 'holiday':
    default:
      return { bg: '#162a4a', border: 'transparent', tone: DARK_THEME.textMuted };
  }
}

function MonthCalendar({
  year,
  month,
  days,
}: {
  year: number;
  month: number;
  days: HoursBalanceDailyEntry[];
}) {
  const monthDays = days.filter((d) => {
    const dt = new Date(d.day);
    return dt.getFullYear() === year && dt.getMonth() + 1 === month;
  });
  const firstDay = new Date(year, month - 1, 1);
  const lastDay = new Date(year, month, 0);
  const startWeekday = (firstDay.getDay() + 6) % 7; // 0=Пн
  const cells: (HoursBalanceDailyEntry | null)[] = [];
  for (let i = 0; i < startWeekday; i++) cells.push(null);
  for (let d = 1; d <= lastDay.getDate(); d++) {
    const dateStr = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    cells.push(monthDays.find((x) => x.day === dateStr) ?? {
      day: dateStr, norm: 0, fact: 0, delta: 0, kind: 'holiday', absence_label: null,
    });
  }
  const balance = monthDays.reduce((s, x) => s + x.delta, 0);

  return (
    <div style={{ background: 'var(--mini-tile-bg, #143258)', padding: 12, borderRadius: 8 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <div style={{ color: DARK_THEME.textPrimary, fontSize: 13, fontWeight: 600 }}>
          {MONTH_NAMES_RU[month - 1]}
        </div>
        <div style={{
          fontSize: 11, padding: '2px 6px', borderRadius: 4,
          color: balanceColor(balance), background: 'rgba(255,255,255,.05)',
        }}>
          {balance > 0 ? '+' : ''}{Math.round(balance)}ч
        </div>
      </div>
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)',
        gap: 2, fontSize: 9, color: DARK_THEME.textMuted, marginBottom: 4,
      }}>
        {WEEKDAY_LABELS.map((w) => (
          <div key={w} style={{ textAlign: 'center' }}>{w}</div>
        ))}
      </div>
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)',
        gap: 2,
      }}>
        {cells.map((c, i) => {
          if (!c) return <div key={i} style={{ height: 24 }} />;
          const { bg, border, tone } = dayBg(c.kind);
          const base = c.kind === 'absence'
            ? c.absence_label ?? 'Отсутствие'
            : `Норма ${c.norm}ч / Факт ${c.fact}ч / ${c.delta > 0 ? '+' : ''}${c.delta}ч`;
          const tip = c.kind === 'overtime' && c.absence_label
            ? `${c.absence_label} · работал ${c.fact}ч / +${c.delta}ч`
            : base;
          return (
            <Tooltip key={i} title={tip}>
              <div style={{
                height: 24, background: bg,
                border: `1px solid ${border}`, borderRadius: 3,
                fontSize: 9, color: tone,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                position: 'relative',
              }}>
                {new Date(c.day).getDate()}
                {c.kind === 'overtime' && (
                  <span style={{
                    position: 'absolute', bottom: 1, right: 2,
                    fontSize: 7, color: '#fff', fontWeight: 700,
                  }}>+{formatDelta(c.delta)}</span>
                )}
                {c.kind === 'skip' && (
                  <span style={{
                    position: 'absolute', bottom: 1, right: 2,
                    fontSize: 7, color: '#fff', fontWeight: 700,
                  }}>{formatDelta(c.delta)}</span>
                )}
              </div>
            </Tooltip>
          );
        })}
      </div>
    </div>
  );
}

function KpiTile({
  label, value, caption, color,
}: {
  label: string; value: string; caption: string; color: string;
}) {
  return (
    <div style={{
      background: 'var(--mini-tile-bg, #143258)', border: `1px solid ${DARK_THEME.border}`, borderRadius: 10, padding: 16,
    }}>
      <div style={{ fontSize: 12, color: DARK_THEME.textMuted, marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 28, fontWeight: 700, color }}>{value}</div>
      {caption && (
        <div style={{ fontSize: 11, color: DARK_THEME.textMuted, marginTop: 4 }}>
          {caption}
        </div>
      )}
    </div>
  );
}

export default function HoursBalanceModal({ employeeId, onClose }: Props) {
  const { data, isLoading } = useHoursBalanceDetail(employeeId);

  return (
    <Modal
      open={employeeId !== null}
      onCancel={onClose}
      width={920}
      footer={null}
      styles={{ body: { padding: 24 } }}
      title={
        data ? (
          <div>
            <div style={{ color: DARK_THEME.textPrimary }}>
              Баланс часов — {data.employee.full_name}
            </div>
            <div style={{ color: DARK_THEME.textMuted, fontSize: 12, fontWeight: 400 }}>
              {data.employee.role_label ?? '—'}
              {data.employee.team_label ? ` · команда ${data.employee.team_label}` : ''}
              {` · с ${data.period.from.split('-').reverse().join('.')}`}
            </div>
          </div>
        ) : 'Загрузка...'
      }
    >
      {isLoading || !data ? (
        <Spin />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* KPI tiles */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
            <KpiTile
              label="Баланс"
              value={`${data.kpi.balance_hours > 0 ? '+' : ''}${Math.round(data.kpi.balance_hours)}ч`}
              caption={`за ${data.period.working_days} рабочих дней`}
              color={balanceColor(data.kpi.balance_hours)}
            />
            <KpiTile
              label="Переработки"
              value={`${data.kpi.overtime_days} дн / +${Math.round(data.kpi.overtime_hours)}ч`}
              caption=""
              color="#ff4d4f"
            />
            <KpiTile
              label="Автоотгулы"
              value={`${data.kpi.skip_days} дн / ${Math.round(data.kpi.skip_hours)}ч`}
              caption=""
              color="#a4b8d8"
            />
          </div>
          {/* Monthly strip */}
          <div style={{ display: 'flex', gap: 8, overflowX: 'auto' }}>
            {data.monthly.map((m) => (
              <div key={`${m.year}-${m.month}`} style={{
                flex: '0 0 130px', background: 'var(--mini-tile-bg, #143258)', padding: 10, borderRadius: 6,
              }}>
                <div style={{
                  fontSize: 10, textTransform: 'uppercase',
                  color: DARK_THEME.textMuted, marginBottom: 4,
                }}>{m.label}</div>
                <div style={{
                  fontSize: 18, fontWeight: 700, color: balanceColor(m.balance),
                }}>
                  {m.balance > 0 ? '+' : ''}{Math.round(m.balance)}ч
                </div>
                <div style={{ fontSize: 10, color: DARK_THEME.textMuted, marginTop: 2 }}>
                  {m.overtime_days} / {m.skip_days}
                </div>
              </div>
            ))}
          </div>
          {/* Calendar grid */}
          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12,
          }}>
            {data.monthly.map((m) => (
              <MonthCalendar
                key={`${m.year}-${m.month}`}
                year={m.year}
                month={m.month}
                days={data.days}
              />
            ))}
          </div>
          {/* Legend */}
          <div style={{
            display: 'flex', gap: 16, fontSize: 11, color: DARK_THEME.textMuted,
            flexWrap: 'wrap',
          }}>
            <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ display: 'inline-block', width: 12, height: 12, borderRadius: 2, background: '#1d3d22', border: '1px solid #52c41a' }} /> норма
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ display: 'inline-block', width: 12, height: 12, borderRadius: 2, background: '#3d1b1d', border: '1px solid #ff4d4f' }} /> переработка
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ display: 'inline-block', width: 12, height: 12, borderRadius: 2, background: '#2a2f42', border: '1px solid #6e7a99' }} /> автоотгул
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ display: 'inline-block', width: 12, height: 12, borderRadius: 2, background: '#3b3155', border: '1px solid #6e5fb0' }} /> отпуск/больничный
            </span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
              <span style={{ display: 'inline-block', width: 12, height: 12, borderRadius: 2, background: '#162a4a' }} /> выходной/праздник
            </span>
          </div>
          <div style={{ fontSize: 11, color: DARK_THEME.textMuted, fontStyle: 'italic' }}>
            Детали задач — в Jira.
          </div>
        </div>
      )}
    </Modal>
  );
}
