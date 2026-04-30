import { Card, Spin, Empty } from 'antd';
import { useNavigate } from 'react-router';
import type { DashboardProjectsResponse, ProjectItem } from '../../types/api';

const STATUS_COLORS = {
  done: '#67d68d',
  indeterminate: '#00c9c8',
  new: '#7e94b8',
  overdue: '#ff4d4f',
};

const SILENCE_THRESHOLD = 14;
const DUE_SOON_THRESHOLD = 7;

function loadColor(pct: number): string {
  if (pct > 110) return '#ff4d4f';
  if (pct >= 70) return '#67d68d';
  return '#faad14';
}

function dueColor(days: number | null): string {
  if (days == null) return '#7e94b8';
  if (days < 0) return '#ff4d4f';
  if (days <= DUE_SOON_THRESHOLD) return '#faad14';
  return '#67d68d';
}

function trendArrow(dir: 'up' | 'down' | 'flat'): { glyph: string; color: string } {
  if (dir === 'up') return { glyph: '↑', color: '#67d68d' };
  if (dir === 'down') return { glyph: '↓', color: '#faad14' };
  return { glyph: '·', color: '#7e94b8' };
}

function Donut({ data }: { data: DashboardProjectsResponse }) {
  const segments = [
    { name: 'Выполнены', value: data.done, color: STATUS_COLORS.done },
    { name: 'В работе', value: data.in_progress, color: STATUS_COLORS.indeterminate },
    { name: 'Просрочены', value: data.overdue, color: STATUS_COLORS.overdue },
    { name: 'Не начаты', value: data.not_started, color: STATUS_COLORS.new },
  ];
  const total = data.total;
  const visible = segments.filter((s) => s.value > 0);

  const cx = 90, cy = 90, r = 72, ir = 56;
  let cum = 0;
  const arcs = visible.map((seg) => {
    const frac = total > 0 ? seg.value / total : 0;
    const startAngle = cum * 360;
    cum += frac;
    const endAngle = cum * 360;
    const sweep = endAngle - startAngle - 2;
    const sa = ((startAngle + 1) - 90) * Math.PI / 180;
    const ea = ((startAngle + 1 + sweep) - 90) * Math.PI / 180;
    const x1 = cx + r * Math.cos(sa), y1 = cy + r * Math.sin(sa);
    const x2 = cx + r * Math.cos(ea), y2 = cy + r * Math.sin(ea);
    const largeArc = sweep > 180 ? 1 : 0;
    return { color: seg.color, d: `M ${x1} ${y1} A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}` };
  });

  return (
    <div>
      <div style={{ position: 'relative', width: 180, height: 180, margin: '0 auto' }}>
        <svg width="180" height="180">
          {arcs.map((a, i) => (
            <path key={i} d={a.d} fill="none" stroke={a.color} strokeWidth={r - ir} />
          ))}
        </svg>
        <div style={{
          position: 'absolute', top: '50%', left: '50%',
          transform: 'translate(-50%, -50%)', textAlign: 'center', pointerEvents: 'none',
        }}>
          <div style={{ fontSize: 32, fontWeight: 700, color: '#fff', lineHeight: 1 }}>{total}</div>
          <div style={{ fontSize: 12, color: '#7e94b8' }}>проектов</div>
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 12 }}>
        {segments.map((s) => (
          <div key={s.name} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: s.color, flexShrink: 0 }} />
            <span style={{ color: '#fff', fontWeight: 600, width: 28 }}>{s.value}</span>
            <span style={{ color: '#7e94b8' }}>{s.name}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function AssigneeStack({ project }: { project: ProjectItem }) {
  const extra = project.assignees_total - project.assignees.length;
  return (
    <div style={{ display: 'flex', alignItems: 'center' }}>
      {project.assignees.map((a, i) => (
        <div
          key={i}
          title={a.initials}
          style={{
            width: 24, height: 24, borderRadius: '50%',
            border: '2px solid #0f2340', background: a.color,
            color: '#fff', fontSize: 10, fontWeight: 700,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            marginLeft: i === 0 ? 0 : -8,
          }}
        >
          {a.initials}
        </div>
      ))}
      {extra > 0 && (
        <div style={{
          width: 24, height: 24, borderRadius: '50%',
          border: '2px solid #0f2340', background: '#1c3358',
          color: '#a4b8d8', fontSize: 10, fontWeight: 700,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          marginLeft: -8,
        }}>+{extra}</div>
      )}
    </div>
  );
}

function ProjectRow({ project, onClick }: { project: ProjectItem; onClick: () => void }) {
  const isDone = project.status_category === 'done';
  const overrun = project.fact_hours > project.plan_hours && project.plan_hours > 0;
  const pct = project.plan_hours > 0 ? (project.fact_hours / project.plan_hours) * 100 : 0;
  const barColor = STATUS_COLORS[project.status_category] || '#7e94b8';
  const fillWidth = Math.min(100, pct);
  const trend = trendArrow(project.trend_dir);
  const fmtDate = (s: string | null) => s ? new Date(s).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }) : '—';

  return (
    <div
      onClick={onClick}
      style={{
        display: 'grid',
        gridTemplateColumns: '12px minmax(220px,1.3fr) 70px 70px 95px 75px 85px 1fr 80px 50px',
        gap: 10,
        padding: '8px 0',
        alignItems: 'center',
        borderBottom: '1px solid rgba(28,51,88,.4)',
        cursor: 'pointer',
        fontSize: 13,
      }}
    >
      <span style={{ width: 8, height: 8, borderRadius: '50%', background: barColor }} />
      <div style={{
        color: isDone ? '#7e94b8' : '#fff',
        textDecoration: isDone ? 'line-through' : 'none',
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        fontSize: 14,
        display: 'flex', alignItems: 'center', gap: 6,
      }}>
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{project.title}</span>
        {project.silent_days > SILENCE_THRESHOLD && !isDone && (
          <span style={{ background: '#faad1422', color: '#faad14', fontSize: 10, padding: '2px 6px', borderRadius: 4, flexShrink: 0 }}>
            тишина {project.silent_days}д
          </span>
        )}
        {overrun && (
          <span style={{ background: '#ff4d4f22', color: '#ff4d4f', fontSize: 10, padding: '2px 6px', borderRadius: 4, flexShrink: 0 }}>
            +{Math.round(project.delta_hours)} ч
          </span>
        )}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 12 }}>
        <span style={{ color: '#a4b8d8' }}>{project.subtasks_done}/{project.subtasks_total}</span>
        <div style={{ height: 5, background: '#1c3358', borderRadius: 2, overflow: 'hidden' }}>
          <div style={{
            height: '100%',
            width: `${project.subtasks_total > 0 ? (project.subtasks_done / project.subtasks_total) * 100 : 0}%`,
            background: barColor,
          }} />
        </div>
      </div>
      <AssigneeStack project={project} />
      <div style={{ fontSize: 13, color: dueColor(project.days_to_due) }}>
        {project.due_date ? `${fmtDate(project.due_date)} · ${project.days_to_due}д` : '—'}
      </div>
      <div style={{ fontSize: 13, color: trend.color }}>
        {trend.glyph} {project.trend_hours_week.toFixed(0)} ч
      </div>
      <div style={{ fontSize: 13, color: project.forecast_close_date ? (project.forecast_in_quarter ? '#67d68d' : '#ff4d4f') : '#7e94b8' }}>
        {isDone ? 'завершён' : project.forecast_close_date ? `к ${fmtDate(project.forecast_close_date)}${project.forecast_in_quarter ? '' : ' ⚠'}` : '—'}
      </div>
      <div style={{ height: 12, background: '#1c3358', borderRadius: 6, overflow: 'visible', position: 'relative' }}>
        <div style={{
          position: 'absolute', top: 0, left: 0, height: '100%',
          width: `${fillWidth}%`,
          background: barColor,
          borderRadius: 6,
        }} />
      </div>
      <div style={{ textAlign: 'right', fontSize: 14, fontWeight: 600, color: '#a4b8d8' }}>
        {Math.round(project.fact_hours)} / {Math.round(project.plan_hours)} ч
      </div>
      <div style={{ textAlign: 'right', fontSize: 14, fontWeight: 700, color: loadColor(pct) }}>
        {Math.round(pct)}%
      </div>
    </div>
  );
}

function KpiTiles({ data }: { data: DashboardProjectsResponse }) {
  const tiles = [
    {
      label: 'ВСЕГО ФАКТОМ',
      value: `${Math.round(data.total_fact_hours)} ч`,
      sub: `из ${Math.round(data.total_plan_hours)} план`,
      color: '#fff',
    },
    {
      label: 'СРЕДНЯЯ ЗАГРУЗКА',
      value: `${Math.round(data.avg_load_pct)}%`,
      sub: 'факт / план',
      color: loadColor(data.avg_load_pct),
    },
    {
      label: 'МОЛЧАТ > 14 ДНЕЙ',
      value: `${data.silent_count}`,
      sub: 'проекта без активности',
      color: data.silent_count > 0 ? '#faad14' : '#7e94b8',
    },
    {
      label: 'ЗАКРОЮТСЯ В СРОК',
      value: `${data.forecast_done}`,
      sub: `(${data.forecast_pct}%) прогноз по темпу`,
      color: '#67d68d',
    },
  ];
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
      {tiles.map((t) => (
        <div key={t.label} style={{
          background: '#0a1d3a', border: '1px solid #1c3358', borderRadius: 8,
          padding: 12, display: 'flex', flexDirection: 'column', gap: 4,
        }}>
          <div style={{ fontSize: 12, color: '#7e94b8', textTransform: 'uppercase', letterSpacing: '0.06em' }}>{t.label}</div>
          <div style={{ fontSize: 32, fontWeight: 700, color: t.color, lineHeight: 1 }}>{t.value}</div>
          <div style={{ fontSize: 13, color: '#7e94b8' }}>{t.sub}</div>
        </div>
      ))}
    </div>
  );
}

function Sparklines({ projects }: { projects: ProjectItem[] }) {
  const visible = projects.slice(0, 6);
  return (
    <div style={{ background: '#0a1d3a', border: '1px solid #1c3358', borderRadius: 8, padding: 14 }}>
      <div style={{
        fontSize: 12, color: '#7e94b8', textTransform: 'uppercase',
        letterSpacing: '0.06em', marginBottom: 10,
      }}>
        Активность по неделям
      </div>
      {visible.map((p) => {
        const max = Math.max(...p.weekly_activity, 1);
        const points = p.weekly_activity
          .map((v, i) => `${(i / Math.max(1, p.weekly_activity.length - 1)) * 100},${100 - (v / max) * 100}`)
          .join(' ');
        const isActive = p.silent_days <= SILENCE_THRESHOLD;
        const stroke = isActive
          ? (p.status_category === 'overdue' || p.fact_hours > p.plan_hours ? '#ff4d4f' : (p.status_category === 'done' ? '#67d68d' : '#00c9c8'))
          : '#2a4060';
        return (
          <div key={p.issue_key} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0' }}>
            <div style={{
              width: 110, fontSize: 14, color: isActive ? '#e6edf7' : '#7e94b8',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {p.title.split(' ').slice(0, 2).join(' ')}
            </div>
            <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ flex: 1, height: 24 }}>
              <polyline
                points={points}
                fill="none"
                stroke={stroke}
                strokeWidth={2}
                strokeDasharray={isActive ? undefined : '3 3'}
                vectorEffect="non-scaling-stroke"
              />
            </svg>
          </div>
        );
      })}
    </div>
  );
}

interface Props {
  data: DashboardProjectsResponse | undefined;
  loading: boolean;
}

export default function ProjectsWidget({ data, loading }: Props) {
  const navigate = useNavigate();

  if (loading) return <Card title="Проекты квартала"><Spin /></Card>;
  if (!data) return <Card title="Проекты квартала"><Empty description="Нет данных" /></Card>;

  return (
    <Card title="Проекты квартала">
      <div style={{ display: 'grid', gridTemplateColumns: '220px 1fr 280px 280px', gap: 20, alignItems: 'flex-start' }}>
        <Donut data={data} />

        <div>
          <div style={{
            display: 'grid',
            gridTemplateColumns: '12px minmax(220px,1.3fr) 70px 70px 95px 75px 85px 1fr 80px 50px',
            gap: 10,
            fontSize: 12,
            color: '#7e94b8',
            textTransform: 'uppercase',
            letterSpacing: '0.04em',
            paddingBottom: 8,
            borderBottom: '1px solid #1c3358',
          }}>
            <span />
            <span>Проект</span>
            <span>Подзад</span>
            <span>Команда</span>
            <span>Срок</span>
            <span>Тренд</span>
            <span>Прогноз</span>
            <span>Прогресс</span>
            <span style={{ textAlign: 'right' }}>Факт / План</span>
            <span style={{ textAlign: 'right' }}>%</span>
          </div>
          {data.projects.map((p) => (
            <ProjectRow
              key={p.issue_key}
              project={p}
              onClick={() => navigate(`/analytics?project=${p.issue_key}`)}
            />
          ))}
          {data.projects.length === 0 && (
            <div style={{ padding: 16, color: '#7e94b8', fontSize: 13 }}>Нет проектов в утверждённом сценарии квартала</div>
          )}
        </div>

        <KpiTiles data={data} />

        <Sparklines projects={data.projects} />
      </div>
    </Card>
  );
}
