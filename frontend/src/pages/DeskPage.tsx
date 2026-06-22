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
 * Приоритетные виджеты сотрудника — каждый во всю ширину, по порядку:
 *   my_tasks → my_timeline → team_availability → awaiting_reaction.
 * Второстепенное опускается вниз: виды работ, баланс+календарь (пополам),
 * отсутствия команды (всегда последним и во всю ширину).
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

  const fullRow = (key: string) => {
    if (!present.has(key)) return;
    rows.push(
      <div className="desk-row" key={`row-${key}`}>
        <div className="desk-col" style={{ flex: '1 1 100%' }}>{W(key)}</div>
      </div>,
    );
    rendered.add(key);
  };

  // Приоритетный блок — каждый виджет во всю ширину.
  fullRow('my_tasks');
  fullRow('my_timeline');
  fullRow('team_availability');
  fullRow('awaiting_reaction');

  // Второстепенное — виды работ во всю ширину.
  fullRow('category_breakdown');

  // Баланс часов + производственный календарь — пополам.
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

  // Прочие нераспределённые виджеты (кроме отсутствий) — во всю ширину.
  widgets
    .filter((k) => !rendered.has(k) && k !== 'team_absences')
    .forEach(fullRow);

  // team_absences — всегда во всю ширину и последним.
  fullRow('team_absences');

  return <div className="desk-grid">{rows}</div>;
}
