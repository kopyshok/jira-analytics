import { useState } from 'react';
import { Card, Spin, Empty, Popover, Button, Checkbox, Space, Tag } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router';
import type { DashboardProjectsResponse, ProjectItem } from '../../types/api';
import { statusTagColor } from '../../utils/status';
import { DARK_THEME, CHART_COLORS } from '../../utils/constants';

const STATUS_COLORS = {
  done: '#67d68d',
  indeterminate: CHART_COLORS.cyan,
  new: DARK_THEME.textMuted,
  overdue: '#ff4d4f',
};

const SILENCE_THRESHOLD = 14;
const DUE_SOON_THRESHOLD = 7;

type ColKey = 'status' | 'subtasks' | 'help' | 'assignees' | 'due' | 'trend' | 'forecast' | 'progress' | 'factplan' | 'pct';
type BlockKey = 'donut' | 'kpi' | 'sparklines';

const COLS: { key: ColKey; label: string; width: string; align?: 'right' }[] = [
  { key: 'status', label: 'Статус', width: 'minmax(0,150px)' },
  { key: 'subtasks', label: 'Задачи', width: '70px' },
  { key: 'help', label: 'Помощь', width: '95px' },
  { key: 'assignees', label: 'Команда', width: '70px' },
  { key: 'due', label: 'Срок', width: '95px' },
  { key: 'trend', label: 'Тренд', width: '75px' },
  { key: 'forecast', label: 'Прогноз', width: '85px' },
  { key: 'progress', label: 'Прогресс', width: 'minmax(80px,160px)' },
  { key: 'factplan', label: 'Факт / План', width: '80px', align: 'right' },
  { key: 'pct', label: '%', width: '50px', align: 'right' },
];

const BLOCKS: { key: BlockKey; label: string }[] = [
  { key: 'donut', label: 'Сводка по статусам' },
  { key: 'kpi', label: 'KPI плитки' },
  { key: 'sparklines', label: 'Активность по неделям' },
];

const STORAGE_KEY = 'dashboard.projects.prefs';

type Prefs = {
  cols: Record<ColKey, boolean>;
  blocks: Record<BlockKey, boolean>;
};

const DEFAULT_PREFS: Prefs = {
  cols: { status: true, subtasks: true, help: true, assignees: true, due: true, trend: true, forecast: true, progress: true, factplan: true, pct: true },
  blocks: { donut: true, kpi: true, sparklines: true },
};

function loadPrefs(): Prefs {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_PREFS;
    const parsed = JSON.parse(raw) as Partial<Prefs>;
    return {
      cols: { ...DEFAULT_PREFS.cols, ...(parsed.cols ?? {}) },
      blocks: { ...DEFAULT_PREFS.blocks, ...(parsed.blocks ?? {}) },
    };
  } catch {
    return DEFAULT_PREFS;
  }
}

function savePrefs(prefs: Prefs) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    // ignore
  }
}

function loadColor(pct: number): string {
  if (pct > 110) return '#ff4d4f';
  if (pct >= 70) return '#67d68d';
  return '#faad14';
}

function dueColor(days: number | null): string {
  if (days == null) return DARK_THEME.textMuted;
  if (days < 0) return '#ff4d4f';
  if (days <= DUE_SOON_THRESHOLD) return '#faad14';
  return '#67d68d';
}

function trendArrow(dir: 'up' | 'down' | 'flat'): { glyph: string; color: string } {
  if (dir === 'up') return { glyph: '↑', color: '#67d68d' };
  if (dir === 'down') return { glyph: '↓', color: '#faad14' };
  return { glyph: '·', color: DARK_THEME.textMuted };
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
          <div style={{ fontSize: 32, fontWeight: 700, color: DARK_THEME.textPrimary, lineHeight: 1 }}>{total}</div>
          <div style={{ fontSize: 12, color: DARK_THEME.textMuted }}>проектов</div>
        </div>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, marginTop: 12 }}>
        {segments.map((s) => (
          <div key={s.name} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: s.color, flexShrink: 0 }} />
            <span style={{ color: DARK_THEME.textPrimary, fontWeight: 600, width: 28 }}>{s.value}</span>
            <span style={{ color: DARK_THEME.textMuted }}>{s.name}</span>
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
            border: `2px solid ${DARK_THEME.cardBg}`, background: a.color,
            color: DARK_THEME.textPrimary, fontSize: 10, fontWeight: 700,
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
          border: `2px solid ${DARK_THEME.cardBg}`, background: DARK_THEME.darkRows,
          color: '#a4b8d8', fontSize: 10, fontWeight: 700,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          marginLeft: -8,
        }}>+{extra}</div>
      )}
    </div>
  );
}

function AlienHelpersStack({ project }: { project: ProjectItem }) {
  if (project.alien_helper_count === 0) {
    return <span style={{ color: DARK_THEME.textMuted, fontSize: 12 }}>—</span>;
  }
  const extra = project.alien_helper_count - project.alien_helpers.length;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <div style={{ display: 'flex', alignItems: 'center' }}>
        {project.alien_helpers.map((a, i) => (
          <div
            key={i}
            title={a.initials}
            style={{
              width: 22, height: 22, borderRadius: '50%',
              border: `2px solid ${DARK_THEME.cardBg}`,
              background: 'linear-gradient(135deg, #84cc16 0%, #22c55e 100%)',
              color: '#052e16', fontSize: 9, fontWeight: 700,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              marginLeft: i === 0 ? 0 : -6,
            }}
          >
            {a.initials}
          </div>
        ))}
        {extra > 0 && (
          <div style={{
            width: 22, height: 22, borderRadius: '50%',
            border: `2px solid ${DARK_THEME.cardBg}`,
            background: 'rgba(132,204,22,0.15)', color: '#84cc16',
            fontSize: 9, fontWeight: 700,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            marginLeft: -6,
          }}>+{extra}</div>
        )}
      </div>
      <span style={{ fontSize: 11, color: '#84cc16', fontWeight: 600 }}>
        +{Math.round(project.alien_fact_hours)}ч
      </span>
    </div>
  );
}

function renderCell(key: ColKey, project: ProjectItem, ctx: { isDone: boolean; pct: number; barColor: string }) {
  const fmtDate = (s: string | null) => s ? new Date(s).toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' }) : '—';
  switch (key) {
    case 'status': {
      const cat = project.status_category === 'overdue' ? 'indeterminate' : project.status_category;
      return project.status
        ? (
          <Tag
            color={statusTagColor(project.status, cat)}
            title={project.status}
            style={{
              marginInlineEnd: 0,
              maxWidth: '100%',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {project.status}
          </Tag>
        )
        : <span style={{ color: DARK_THEME.textMuted, fontSize: 13 }}>—</span>;
    }
    case 'subtasks':
      return (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 12 }}>
          <span style={{ color: '#a4b8d8' }}>{project.subtasks_done}/{project.subtasks_total}</span>
          <div style={{ height: 5, background: DARK_THEME.darkRows, borderRadius: 2, overflow: 'hidden' }}>
            <div style={{
              height: '100%',
              width: `${project.subtasks_total > 0 ? (project.subtasks_done / project.subtasks_total) * 100 : 0}%`,
              background: ctx.barColor,
            }} />
          </div>
        </div>
      );
    case 'help':
      return <AlienHelpersStack project={project} />;
    case 'assignees':
      return <AssigneeStack project={project} />;
    case 'due':
      return (
        <div style={{ fontSize: 13, color: dueColor(project.days_to_due) }}>
          {project.due_date ? `${fmtDate(project.due_date)} · ${project.days_to_due}д` : '—'}
        </div>
      );
    case 'trend': {
      const trend = trendArrow(project.trend_dir);
      return (
        <div style={{ fontSize: 13, color: trend.color }}>
          {trend.glyph} {project.trend_hours_week.toFixed(0)} ч
        </div>
      );
    }
    case 'forecast':
      return (
        <div style={{ fontSize: 13, color: project.forecast_close_date ? (project.forecast_in_quarter ? '#67d68d' : '#ff4d4f') : DARK_THEME.textMuted }}>
          {ctx.isDone ? 'завершён' : project.forecast_close_date ? `к ${fmtDate(project.forecast_close_date)}${project.forecast_in_quarter ? '' : ' ⚠'}` : '—'}
        </div>
      );
    case 'progress': {
      const fillWidth = Math.min(100, ctx.pct);
      return (
        <div style={{ height: 12, background: DARK_THEME.darkRows, borderRadius: 6, overflow: 'visible', position: 'relative' }}>
          <div style={{
            position: 'absolute', top: 0, left: 0, height: '100%',
            width: `${fillWidth}%`,
            background: ctx.barColor,
            borderRadius: 6,
          }} />
        </div>
      );
    }
    case 'factplan':
      return (
        <div style={{ textAlign: 'right', fontSize: 14, fontWeight: 600, color: '#a4b8d8' }}>
          {Math.round(project.team_fact_hours)} / {Math.round(project.plan_hours)} ч
        </div>
      );
    case 'pct':
      return (
        <div style={{ textAlign: 'right', fontSize: 14, fontWeight: 700, color: loadColor(ctx.pct) }}>
          {Math.round(ctx.pct)}%
        </div>
      );
  }
}

function ProjectRow({
  project,
  onClick,
  visibleCols,
  gridTemplate,
}: {
  project: ProjectItem;
  onClick: () => void;
  visibleCols: ColKey[];
  gridTemplate: string;
}) {
  const isDone = project.status_category === 'done';
  const overrun = project.team_fact_hours > project.plan_hours && project.plan_hours > 0;
  const pct = project.plan_hours > 0 ? (project.team_fact_hours / project.plan_hours) * 100 : 0;
  const barColor = STATUS_COLORS[project.status_category] || DARK_THEME.textMuted;

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onClick(); } }}
      style={{
        display: 'grid',
        gridTemplateColumns: gridTemplate,
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
        color: isDone ? DARK_THEME.textMuted : DARK_THEME.textPrimary,
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
            +{Math.round(project.team_fact_hours - project.plan_hours)} ч
          </span>
        )}
      </div>
      {visibleCols.map((key) => (
        <div key={key} style={{ minWidth: 0, overflow: 'hidden' }}>{renderCell(key, project, { isDone, pct, barColor })}</div>
      ))}
    </div>
  );
}

function KpiTiles({ data }: { data: DashboardProjectsResponse }) {
  const tiles = [
    {
      label: 'ВСЕГО ФАКТОМ',
      value: `${Math.round(data.total_team_fact_hours)} ч`,
      sub: `из ${Math.round(data.total_plan_hours)} план`,
      color: DARK_THEME.textPrimary,
    },
    {
      label: 'СРЕДНЯЯ ЗАГРУЗКА',
      value: `${Math.round(data.avg_load_pct)}%`,
      sub: 'факт / план',
      color: loadColor(data.avg_load_pct),
    },
    {
      label: 'ПОМОЩЬ ИЗВНЕ',
      value: data.total_alien_fact_hours > 0 ? `+${Math.round(data.total_alien_fact_hours)} ч` : '—',
      sub: data.total_alien_fact_hours > 0
        ? `${data.alien_helper_count} чел · ${data.alien_projects_count} проектов`
        : 'нет внешней помощи',
      color: data.total_alien_fact_hours > 0 ? '#84cc16' : DARK_THEME.textMuted,
    },
    {
      label: 'МОЛЧАТ > 14 ДНЕЙ',
      value: `${data.silent_count}`,
      sub: 'проекта без активности',
      color: data.silent_count > 0 ? '#faad14' : DARK_THEME.textMuted,
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
      {tiles.map((t, idx) => {
        const isHelp = t.label === 'ПОМОЩЬ ИЗВНЕ' && data.total_alien_fact_hours > 0;
        return (
          <div key={t.label} style={{
            background: isHelp ? 'rgba(132,204,22,0.06)' : DARK_THEME.cardBg,
            border: isHelp ? '1px solid rgba(132,204,22,0.25)' : `1px solid ${DARK_THEME.darkRows}`,
            borderRadius: 8,
            padding: 12, display: 'flex', flexDirection: 'column', gap: 4,
            gridColumn: idx === tiles.length - 1 && tiles.length % 2 === 1 ? '1 / -1' : undefined,
          }}>
            <div style={{ fontSize: 12, color: DARK_THEME.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{t.label}</div>
            <div style={{ fontSize: 32, fontWeight: 700, color: t.color, lineHeight: 1 }}>{t.value}</div>
            <div style={{ fontSize: 13, color: DARK_THEME.textMuted }}>{t.sub}</div>
          </div>
        );
      })}
    </div>
  );
}

function Sparklines({ projects }: { projects: ProjectItem[] }) {
  const visible = [...projects].sort((a, b) => b.team_fact_hours - a.team_fact_hours).slice(0, 6);
  return (
    <div style={{ background: DARK_THEME.cardBg, border: `1px solid ${DARK_THEME.darkRows}`, borderRadius: 8, padding: 14 }}>
      <div style={{
        fontSize: 12, color: DARK_THEME.textMuted, textTransform: 'uppercase',
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
          ? (p.status_category === 'overdue' || p.team_fact_hours > p.plan_hours ? '#ff4d4f' : (p.status_category === 'done' ? '#67d68d' : CHART_COLORS.cyan))
          : '#2a4060';
        return (
          <div key={p.issue_key} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0' }}>
            <div style={{
              width: 110, fontSize: 14, color: isActive ? '#e6edf7' : DARK_THEME.textMuted,
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

function SettingsPopover({ prefs, setPrefs }: { prefs: Prefs; setPrefs: (p: Prefs) => void }) {
  const toggleCol = (k: ColKey, on: boolean) => setPrefs({ ...prefs, cols: { ...prefs.cols, [k]: on } });
  const toggleBlock = (k: BlockKey, on: boolean) => setPrefs({ ...prefs, blocks: { ...prefs.blocks, [k]: on } });

  const content = (
    <Space orientation="vertical" size={12} style={{ minWidth: 220 }}>
      <div>
        <div style={{ fontSize: 12, color: DARK_THEME.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
          Колонки
        </div>
        <Space orientation="vertical" size={4}>
          {COLS.map((c) => (
            <Checkbox
              key={c.key}
              checked={prefs.cols[c.key]}
              onChange={(e) => toggleCol(c.key, e.target.checked)}
            >
              {c.label}
            </Checkbox>
          ))}
        </Space>
      </div>
      <div>
        <div style={{ fontSize: 12, color: DARK_THEME.textMuted, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 8 }}>
          Блоки
        </div>
        <Space orientation="vertical" size={4}>
          {BLOCKS.map((b) => (
            <Checkbox
              key={b.key}
              checked={prefs.blocks[b.key]}
              onChange={(e) => toggleBlock(b.key, e.target.checked)}
            >
              {b.label}
            </Checkbox>
          ))}
        </Space>
      </div>
      <Button size="small" onClick={() => setPrefs(DEFAULT_PREFS)}>
        Сбросить
      </Button>
    </Space>
  );

  return (
    <Popover content={content} title="Настройка вида" trigger="click" placement="bottomRight">
      <Button type="text" icon={<SettingOutlined />} aria-label="Настройка вида" />
    </Popover>
  );
}

interface Props {
  data: DashboardProjectsResponse | undefined;
  loading: boolean;
}

export default function ProjectsWidget({ data, loading }: Props) {
  const navigate = useNavigate();
  const [prefs, setPrefsState] = useState<Prefs>(() => loadPrefs());

  const setPrefs = (p: Prefs) => {
    setPrefsState(p);
    savePrefs(p);
  };

  const extra = <SettingsPopover prefs={prefs} setPrefs={setPrefs} />;

  if (loading) return <Card title="Проекты квартала" extra={extra}><Spin /></Card>;
  if (!data) return <Card title="Проекты квартала" extra={extra}><Empty description="Нет данных" /></Card>;

  const visibleCols = COLS.filter((c) => prefs.cols[c.key]);
  const tableGrid = ['12px', 'minmax(220px,1.3fr)', ...visibleCols.map((c) => c.width)].join(' ');

  const outerCols = [
    prefs.blocks.donut ? '220px' : null,
    '1fr',
    prefs.blocks.kpi ? '280px' : null,
    prefs.blocks.sparklines ? '280px' : null,
  ].filter(Boolean).join(' ');

  return (
    <Card title="Проекты квартала" extra={extra}>
      <div style={{ display: 'grid', gridTemplateColumns: outerCols, gap: 20, alignItems: 'flex-start' }}>
        {prefs.blocks.donut && <Donut data={data} />}

        <div>
          <div style={{
            display: 'grid',
            gridTemplateColumns: tableGrid,
            gap: 10,
            fontSize: 12,
            color: DARK_THEME.textMuted,
            textTransform: 'uppercase',
            letterSpacing: '0.04em',
            paddingBottom: 8,
            borderBottom: `1px solid ${DARK_THEME.darkRows}`,
          }}>
            <span />
            <span>Проект</span>
            {visibleCols.map((c) => (
              <span key={c.key} style={c.align === 'right' ? { textAlign: 'right' } : undefined}>
                {c.label}
              </span>
            ))}
          </div>
          {data.projects.map((p) => (
            <ProjectRow
              key={p.issue_key}
              project={p}
              onClick={() => navigate(`/projects/${encodeURIComponent(p.issue_key)}`)}
              visibleCols={visibleCols.map((c) => c.key)}
              gridTemplate={tableGrid}
            />
          ))}
          {data.projects.length === 0 && (
            <div style={{ padding: 16, color: DARK_THEME.textMuted, fontSize: 13 }}>Нет проектов в утверждённом сценарии квартала</div>
          )}
        </div>

        {prefs.blocks.kpi && <KpiTiles data={data} />}

        {prefs.blocks.sparklines && <Sparklines projects={data.projects} />}
      </div>
    </Card>
  );
}
