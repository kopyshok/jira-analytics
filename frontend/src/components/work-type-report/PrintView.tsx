import { useEffect, useMemo } from 'react';
import { useSearchParams } from 'react-router';
import { Spin, Button, ConfigProvider, theme } from 'antd';
import { PrinterOutlined } from '@ant-design/icons';
import { PieChart, Pie, Cell } from 'recharts';
import { useWorkTypeReport } from '../../hooks/useWorkTypeReport';
import { FONTS, MONTH_NAMES } from '../../utils/constants';
import type { Theme } from '../../types/workTypeReport';
import { buildSlices } from './utils';
import dayjs from 'dayjs';
import 'dayjs/locale/ru';

dayjs.locale('ru');

const OTHER_COLOR = '#9ab0c8';

function TopThemeBlock({ theme, rank }: { theme: Theme; rank: number }) {
  const top3 = theme.top_tasks.slice(0, 3);
  return (
    <div
      className="work-type-print-section"
      style={{ marginBottom: 20, paddingBottom: 16, borderBottom: '1px solid #dde3eb' }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
        <span
          style={{
            display: 'inline-block',
            width: 10,
            height: 10,
            borderRadius: '50%',
            background: theme.color,
            flexShrink: 0,
          }}
        />
        <span
          style={{
            fontWeight: 700,
            fontSize: 14,
            color: '#007575',
          }}
        >
          {rank}. {theme.name}
        </span>
        <span style={{ fontSize: 12, color: '#6b8aaa', marginLeft: 8 }}>
          {Math.round(theme.totals.hours)} ч · {theme.totals.pct.toFixed(1)}%
        </span>
      </div>
      {theme.narrative && (
        <p
          style={{
            fontSize: 12,
            fontStyle: 'italic',
            color: '#4a5568',
            margin: '0 0 8px 20px',
            lineHeight: 1.5,
          }}
        >
          {theme.narrative}
        </p>
      )}
      {top3.length > 0 && (
        <ul style={{ margin: '0 0 0 20px', padding: 0, listStyle: 'none' }}>
          {top3.map((t) => (
            <li key={t.key} style={{ fontSize: 11, color: '#374151', marginBottom: 2 }}>
              <span style={{ fontFamily: 'monospace', fontWeight: 600, color: '#007575' }}>
                {t.key}
              </span>{' '}
              — {t.summary}
              {t.hours > 0 && (
                <span style={{ color: '#9ab0c8', marginLeft: 6 }}>
                  ({Math.round(t.hours)} ч)
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function PrintView() {
  const [sp] = useSearchParams();
  const workTypeId = sp.get('work_type_id') ?? '';
  const year = parseInt(sp.get('year') ?? '0', 10);
  const quarter = parseInt(sp.get('quarter') ?? '0', 10);
  const monthRaw = sp.get('month');
  const month = monthRaw ? parseInt(monthRaw, 10) : undefined;
  const teamsRaw = sp.get('teams');
  const teams = teamsRaw ? teamsRaw.split(',').filter(Boolean) : [];

  const { data: report, isLoading, isError } = useWorkTypeReport(
    { work_type_id: workTypeId, year, quarter, month: month ?? null, teams },
    { enabled: !!(workTypeId && year && quarter) },
  );

  const themes = useMemo(() => report?.data.themes ?? [], [report]);
  const totalsHours = report?.data.totals.hours ?? 0;

  const slices = useMemo(() => buildSlices(themes, totalsHours, OTHER_COLOR), [themes, totalsHours]);

  const top3 = useMemo(
    () => [...themes].sort((a, b) => b.totals.hours - a.totals.hours).slice(0, 3),
    [themes],
  );

  // Add/remove body class to override dark background from projects print CSS
  useEffect(() => {
    document.body.classList.add('work-type-print-active');
    return () => document.body.classList.remove('work-type-print-active');
  }, []);

  if (isLoading) {
    return (
      <div className="work-type-print-view" style={{ display: 'grid', placeItems: 'center', minHeight: '100vh' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (isError || !report) {
    return (
      <div className="work-type-print-view" style={{ padding: 40, color: '#991b1b' }}>
        Не удалось загрузить отчёт. Проверьте параметры URL.
      </div>
    );
  }

  const { data, generated_at, team_set, dictionary_version, model_id, prompt_version } = report;
  const { headline, totals, recommendation, is_fallback_narrative } = data;

  // Period label
  const monthName = month ? MONTH_NAMES[month] : undefined;
  const periodLabel = `${year} Q${quarter}${monthName ? ` · ${monthName}` : ''}`;

  return (
    <div className="work-type-print-view">
      {/* Print button — hidden in actual print */}
      <div className="print-hide-btn" style={{ marginBottom: 20, display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
        <ConfigProvider theme={{ algorithm: theme.defaultAlgorithm }}>
          <Button icon={<PrinterOutlined />} type="primary" onClick={() => window.print()}>
            Печать / PDF
          </Button>
          <Button onClick={() => window.close()}>Закрыть</Button>
        </ConfigProvider>
      </div>

      {/* ── Section 1: Title block ── */}
      <div className="work-type-print-section" style={{ marginBottom: 28, paddingBottom: 16, borderBottom: '2px solid #00c9c8' }}>
        <div style={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em', color: '#6b8aaa', marginBottom: 4 }}>
          Тематический отчёт
        </div>
        <h1 style={{ fontFamily: FONTS.display, fontSize: 28, fontWeight: 700, color: '#1a1a1a', margin: '0 0 6px 0' }}>
          {periodLabel}
        </h1>
        {team_set.length > 0 && (
          <div style={{ fontSize: 12, color: '#4a5568', marginBottom: 4 }}>
            Команды: {team_set.join(', ')}
          </div>
        )}
        <div style={{ fontSize: 11, color: '#9ab0c8' }}>
          Сформировано: {dayjs(generated_at).format('DD MMMM YYYY, HH:mm')}
          {dictionary_version && ` · Словарь v${dictionary_version}`}
          {model_id && ` · ${model_id}`}
          {prompt_version && ` · промпт v${prompt_version}`}
        </div>
      </div>

      {/* ── Section 2: AI Headline ── */}
      <div
        className="work-type-print-section"
        style={{
          boxShadow: 'inset 2px 0 0 #00c9c8',
          background: '#f0fdfc',
          padding: '14px 18px',
          marginBottom: 24,
          borderRadius: 6,
        }}
      >
        <div
          style={{
            fontFamily: FONTS.display,
            fontSize: 18,
            fontWeight: 700,
            color: '#1a1a1a',
            lineHeight: 1.4,
            marginBottom: 6,
          }}
        >
          {headline || 'AI-сводка недоступна'}
        </div>
        <div style={{ fontSize: 11, color: '#6b8aaa', display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          {is_fallback_narrative && (
            <span style={{ color: '#b45309', fontWeight: 600 }}>Шаблонный нарратив (AI недоступен)</span>
          )}
          {!is_fallback_narrative && <span style={{ color: '#065f46', fontWeight: 600 }}>AI-сводка</span>}
          <span>
            {totals.tasks.toLocaleString('ru')} задач · {Math.round(totals.hours).toLocaleString('ru')} ч
          </span>
        </div>
      </div>

      {/* ── Section 3: KPI mini-row ── */}
      <div
        className="work-type-print-section"
        style={{
          display: 'flex',
          gap: 0,
          marginBottom: 24,
          border: '1px solid #dde3eb',
          borderRadius: 8,
          overflow: 'hidden',
        }}
      >
        {[
          { value: Math.round(totals.hours).toLocaleString('ru'), label: 'Часов' },
          { value: String(totals.themes_count), label: 'Тем' },
          { value: totals.tasks.toLocaleString('ru'), label: 'Задач' },
          { value: String(totals.employees), label: 'Сотрудников' },
        ].map((kpi, i) => (
          <div
            key={i}
            style={{
              flex: 1,
              textAlign: 'center',
              padding: '14px 8px',
              borderRight: i < 3 ? '1px solid #dde3eb' : undefined,
            }}
          >
            <div style={{ fontSize: 24, fontWeight: 700, color: '#1a1a1a' }}>{kpi.value}</div>
            <div style={{ fontSize: 11, color: '#6b8aaa' }}>{kpi.label}</div>
          </div>
        ))}
      </div>

      {/* ── Section 4: Donut + bars ── */}
      {themes.length > 0 && (
        <div
          className="work-type-print-section"
          style={{
            display: 'flex',
            gap: 24,
            alignItems: 'flex-start',
            marginBottom: 28,
            padding: '16px',
            border: '1px solid #dde3eb',
            borderRadius: 8,
          }}
        >
          {/* Donut */}
          <div style={{ position: 'relative', width: 160, height: 160, flexShrink: 0 }}>
            <PieChart width={160} height={160}>
              <Pie
                data={slices}
                dataKey="hours"
                innerRadius={50}
                outerRadius={72}
                paddingAngle={1}
                stroke="none"
                isAnimationActive={false}
              >
                {slices.map((s, i) => <Cell key={i} fill={s.color} />)}
              </Pie>
            </PieChart>
            <div
              style={{
                position: 'absolute', inset: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                pointerEvents: 'none',
              }}
            >
              <div style={{ fontSize: 16, fontWeight: 700, color: '#1a1a1a' }}>
                {Math.round(totals.hours)} ч
              </div>
            </div>
          </div>

          {/* Bars */}
          <div style={{ flex: 1, minWidth: 120 }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: '#6b8aaa', marginBottom: 10 }}>
              Распределение тем
            </div>
            {slices.map((s, i) => (
              <div key={i} style={{ marginBottom: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 3 }}>
                  <span style={{ color: '#374151', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '60%' }} title={s.name}>
                    {s.name}
                  </span>
                  <span style={{ color: '#6b8aaa', flexShrink: 0 }}>
                    {Math.round(s.hours)} ч ({s.pct.toFixed(1)}%)
                  </span>
                </div>
                <div style={{ height: 6, background: '#e8edf5', borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: `${Math.min(100, s.pct)}%`, background: s.color, borderRadius: 3 }} />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Section 5: Top-3 themes with narratives ── */}
      {top3.length > 0 && (
        <div className="work-type-print-section" style={{ marginBottom: 28 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#1a1a1a', marginBottom: 14, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Топ-3 темы
          </div>
          {top3.map((t, i) => (
            <TopThemeBlock key={t.theme_id ?? i} theme={t} rank={i + 1} />
          ))}
        </div>
      )}

      {/* ── Section 6: Recommendation ── */}
      {recommendation?.text && (
        <div
          className="work-type-print-section"
          style={{
            boxShadow: 'inset 2px 0 0 #f5c842',
            background: '#fffbeb',
            padding: '14px 18px',
            marginBottom: 24,
            borderRadius: 6,
          }}
        >
          <div style={{ fontSize: 13, fontWeight: 700, color: '#92400e', marginBottom: 6 }}>
            Рекомендация
          </div>
          <div style={{ fontSize: 13, color: '#374151', lineHeight: 1.5, marginBottom: recommendation.expected_impact ? 8 : 0 }}>
            {recommendation.text}
          </div>
          {recommendation.expected_impact && (
            <div style={{ fontSize: 12, color: '#6b8aaa' }}>
              Ожидаемый эффект: <span style={{ color: '#374151' }}>{recommendation.expected_impact}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
