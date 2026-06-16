import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router';
import { ConfigProvider, Result, Spin, theme } from 'antd';
import ruRURaw from 'antd/locale/ru_RU';
import { fetchDeskMeta } from '../api/desk';
import { WIDGET_REGISTRY } from '../components/desk/registry';
import { fmtLongDate, fmtQuarter, fmtSignedHours, initials } from '../components/desk/format';
import '../components/desk/desk-theme.css';

const ruRU = ((ruRURaw as unknown as { default?: typeof ruRURaw }).default
  ?? ruRURaw) as typeof ruRURaw;

type DeskTheme = 'light' | 'dark';

function readStoredTheme(): DeskTheme {
  try {
    return localStorage.getItem('desk-theme') === 'dark' ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

/** AntD-токены, выровненные под десктопную палитру стола (light / dark). */
function antdTokensFor(t: DeskTheme) {
  if (t === 'dark') {
    return {
      colorPrimary: '#36c5d8',
      colorBgContainer: '#22293c',
      colorBgElevated: '#28324a',
      colorText: '#e3e9f5',
      colorBorderSecondary: 'rgba(120,140,170,0.25)',
      borderRadius: 10,
      fontFamily: "'Inter', system-ui, sans-serif",
    };
  }
  return {
    colorPrimary: '#16a5b8',
    colorBgContainer: '#fbfcfd',
    colorBgElevated: '#ffffff',
    colorText: '#26303d',
    colorBorderSecondary: '#dde3ea',
    borderRadius: 10,
    fontFamily: "'Inter', system-ui, sans-serif",
  };
}

export default function DeskPage() {
  const { token = '' } = useParams<{ token: string }>();
  const [deskTheme, setDeskTheme] = useState<DeskTheme>(readStoredTheme);

  useEffect(() => {
    try {
      localStorage.setItem('desk-theme', deskTheme);
    } catch {
      /* private mode — пропускаем */
    }
  }, [deskTheme]);

  const { data, isLoading, isError } = useQuery({
    queryKey: ['desk', token],
    queryFn: ({ signal }) => fetchDeskMeta(token, signal),
    retry: false,
    refetchInterval: 5 * 60_000,
  });

  const antdConfig = {
    algorithm: deskTheme === 'dark' ? theme.darkAlgorithm : theme.defaultAlgorithm,
    token: antdTokensFor(deskTheme),
  };

  if (isLoading) {
    return (
      <ConfigProvider locale={ruRU} theme={antdConfig}>
        <div className="desk-root" data-theme={deskTheme}>
          <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center' }}>
            <Spin size="large" />
          </div>
        </div>
      </ConfigProvider>
    );
  }

  if (isError || !data) {
    return (
      <ConfigProvider locale={ruRU} theme={antdConfig}>
        <div className="desk-root" data-theme={deskTheme}>
          <div style={{ minHeight: '100vh', display: 'grid', placeItems: 'center', padding: 24 }}>
            <Result
              status="404"
              title="Рабочий стол не найден"
              subTitle="Рабочий стол не найден или ссылка отозвана."
            />
          </div>
        </div>
      </ConfigProvider>
    );
  }

  const { employee, teams, enabled_widgets, period, summary } = data;
  const widgets = enabled_widgets.filter((k) => WIDGET_REGISTRY[k]);

  const toggle = () => setDeskTheme((t) => (t === 'dark' ? 'light' : 'dark'));

  return (
    <ConfigProvider locale={ruRU} theme={antdConfig}>
      <div className="desk-root" data-theme={deskTheme}>
        <div className="desk-layout">
          <DeskHeader
            name={employee.display_name}
            teams={teams}
            year={period.year}
            quarter={period.quarter}
            summary={summary}
            deskTheme={deskTheme}
            onToggleTheme={toggle}
          />
          <div className="desk-header-divider" />

          {widgets.length === 0 ? (
            <div className="desk-empty">Виджеты не настроены.</div>
          ) : (
            <DeskLayout token={token} widgets={widgets} />
          )}
        </div>
      </div>
    </ConfigProvider>
  );
}

/* ───────── Header band ───────── */
function DeskHeader({
  name,
  teams,
  year,
  quarter,
  summary,
  deskTheme,
  onToggleTheme,
}: {
  name: string;
  teams: string[];
  year: number;
  quarter: number;
  summary: import('../types/desk').DeskSummary;
  deskTheme: DeskTheme;
  onToggleTheme: () => void;
}) {
  const overtime = summary.overtime_hours;
  const overtimeCls = overtime > 0 ? 'positive' : overtime < 0 ? 'negative' : 'neutral';

  return (
    <div className="desk-header-outer">
      <div className="desk-header">
        <div className="desk-header-left">
          <div className="desk-avatar">{initials(name)}</div>
          <div>
            <div className="desk-user-name">{name}</div>
            {teams.length > 0 && (
              <div className="desk-team-tags">
                {teams.map((t) => (
                  <span key={t} className="desk-team-tag">{t}</span>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="desk-header-right">
          <div className="desk-date-block">
            <div className="desk-date-main">{fmtLongDate(new Date())}</div>
            <div className="desk-quarter">{fmtQuarter(year, quarter)}</div>
            <div className="desk-updated">
              <span className="desk-pulse-dot" />
              обновлено только что
            </div>
          </div>

          <div className="desk-hero-metrics">
            <div className="desk-hero-metric">
              <div className={`desk-hero-val ${overtimeCls}`}>{fmtSignedHours(overtime)}</div>
              <div className="desk-hero-unit">Переработка</div>
            </div>
            <div className="desk-hero-metric">
              <div className="desk-hero-val neutral">{summary.remaining_workdays_month}</div>
              <div className="desk-hero-unit">Рабочих дней до конца месяца</div>
            </div>
            <div className="desk-hero-metric">
              <div className="desk-hero-val neutral">{summary.projects_in_progress}</div>
              <div className="desk-hero-unit">Проектов в работе</div>
            </div>
          </div>

          <div
            className="desk-theme-toggle"
            role="button"
            tabIndex={0}
            aria-label="Переключить тему"
            onClick={onToggleTheme}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onToggleTheme();
              }
            }}
          >
            <span className="desk-theme-knob">{deskTheme === 'dark' ? '☽' : '☀'}</span>
            <span className="desk-theme-label">{deskTheme === 'dark' ? 'Aurora' : 'Porcelain'}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ───────── Key-aware layout ─────────
 * - team_absences          → всегда во всю ширину и последним
 * - hours_balance + production_calendar → одна строка пополам (если оба)
 * - my_tasks (доминанта) + my_timeline  → строка ≈60/40 (если оба)
 * - category_breakdown + team_availability → строка пополам (если оба)
 * - awaiting_reaction и одиночные остатки → адаптивная сетка
 */
function DeskLayout({ token, widgets }: { token: string; widgets: string[] }) {
  const present = new Set(widgets);
  const rendered = new Set<string>();

  const W = (key: string) => {
    const def = WIDGET_REGISTRY[key];
    if (!def) return null;
    const Comp = def.component;
    return <Comp token={token} title={def.title} />;
  };

  const rows: React.ReactNode[] = [];

  // Row: my_tasks + my_timeline (≈60/40)
  if (present.has('my_tasks') || present.has('my_timeline')) {
    const both = present.has('my_tasks') && present.has('my_timeline');
    rows.push(
      <div className="desk-row" key="row-tasks">
        {present.has('my_tasks') && (
          <div className="desk-col" style={{ flex: both ? '1 1 59%' : '1 1 100%' }}>
            {W('my_tasks')}
          </div>
        )}
        {present.has('my_timeline') && (
          <div className="desk-col" style={{ flex: both ? '1 1 38%' : '1 1 100%' }}>
            {W('my_timeline')}
          </div>
        )}
      </div>,
    );
    rendered.add('my_tasks');
    rendered.add('my_timeline');
  }

  // Row: hours_balance + production_calendar (half/half)
  if (present.has('hours_balance') || present.has('production_calendar')) {
    rows.push(
      <div className="desk-row" key="row-hours">
        {present.has('hours_balance') && <div className="desk-col" style={{ flex: '1 1 48%' }}>{W('hours_balance')}</div>}
        {present.has('production_calendar') && <div className="desk-col" style={{ flex: '1 1 52%' }}>{W('production_calendar')}</div>}
      </div>,
    );
    rendered.add('hours_balance');
    rendered.add('production_calendar');
  }

  // Row: category_breakdown + team_availability (half/half)
  if (present.has('category_breakdown') || present.has('team_availability')) {
    rows.push(
      <div className="desk-row" key="row-cat">
        {present.has('category_breakdown') && <div className="desk-col" style={{ flex: '1 1 48%' }}>{W('category_breakdown')}</div>}
        {present.has('team_availability') && <div className="desk-col" style={{ flex: '1 1 52%' }}>{W('team_availability')}</div>}
      </div>,
    );
    rendered.add('category_breakdown');
    rendered.add('team_availability');
  }

  // Прочие одиночные виджеты (включая awaiting_reaction) — по порядку, во всю ширину блоками.
  const leftovers = widgets.filter((k) => !rendered.has(k) && k !== 'team_absences');
  if (leftovers.length > 0) {
    rows.push(
      <div className="desk-row" key="row-rest">
        {leftovers.map((k) => (
          <div className="desk-col" style={{ flex: '1 1 48%' }} key={k}>
            {W(k)}
          </div>
        ))}
      </div>,
    );
  }

  // team_absences — всегда во всю ширину и последним.
  if (present.has('team_absences')) {
    rows.push(
      <div className="desk-row" key="row-absence">
        <div className="desk-col" style={{ flex: '1 1 100%' }}>{W('team_absences')}</div>
      </div>,
    );
  }

  return <div className="desk-grid">{rows}</div>;
}
