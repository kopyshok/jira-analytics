import React from 'react';
import { ProjectHero } from './presentation/ProjectHero';
import { ProjectStorySection } from './presentation/ProjectStorySection';
import { DonutChart } from './shared/DonutChart';
import { StarRating } from './shared/StarRating';
import type { ProjectDetail, ProjectSummary } from '../../types/projects';
import { DARK_THEME } from '../../utils/constants';

interface Props {
  detail: ProjectDetail | undefined;
  summary: ProjectSummary | null | undefined;
}

const COLORS = ['#378ADD', '#1D9E75', '#EF9F27', '#7F77DD', 'var(--text-muted, #7e94b8)', 'var(--text-muted, #7e94b8)', 'var(--text-muted, #7e94b8)'];
const AI_PALETTE = ['#378ADD', '#1D9E75', '#EF9F27', '#7F77DD', '#ff4d4f', '#67d68d'];

function initials(name: string): string {
  return name
    .trim()
    .split(/\s+/)
    .slice(0, 2)
    .map((s) => s[0] ?? '')
    .join('')
    .toUpperCase();
}

const AI_PLACEHOLDER_STYLE: React.CSSProperties = {
  padding: 24,
  background: DARK_THEME.sidebarBg,
  borderRadius: 8,
  color: DARK_THEME.textMuted,
  textAlign: 'center',
  fontStyle: 'italic',
};

export const ProjectPresentationView: React.FC<Props> = ({ detail, summary }) => {
  if (!detail) return null;

  const empMax = Math.max(1, detail.employees[0]?.hours ?? 1);
  const hasRatings =
    detail.rating_quality !== null ||
    detail.rating_speed !== null ||
    detail.rating_result !== null;

  return (
    <div className="presentation-view" style={{ maxWidth: 960, margin: '0 auto' }}>
      <ProjectHero detail={detail} />

      {/* Что мы делали — всегда */}
      <ProjectStorySection title="Что мы делали">
        {summary && summary.goals.length > 0 ? (
          <ol style={{ paddingLeft: 0, listStyle: 'none', margin: 0 }}>
            {summary.goals.map((g, i) => (
              <li key={i} style={{ display: 'flex', gap: 16, marginBottom: 16, fontSize: 16, color: 'var(--text-2, #cfd8e5)' }}>
                <span style={{ flexShrink: 0, fontSize: 28, fontWeight: 700, color: DARK_THEME.cyanPrimary, lineHeight: 1, width: 32 }}>{i + 1}</span>
                <span>{g}</span>
              </li>
            ))}
          </ol>
        ) : (
          <div style={AI_PLACEHOLDER_STYLE}>AI-цели генерируются...</div>
        )}
        {detail.description && (
          <p style={{ marginTop: 16, color: DARK_THEME.textMuted, whiteSpace: 'pre-wrap', fontSize: 14 }}>
            {detail.description.slice(0, 800)}
          </p>
        )}
      </ProjectStorySection>

      {/* Какой результат — всегда */}
      <ProjectStorySection title="Какой результат">
        {summary ? (
          <>
            {summary.result_checklist.length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {summary.result_checklist.map((c, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: 12, fontSize: 16 }}>
                    <span
                      style={{
                        flexShrink: 0,
                        color: c.done ? '#67d68d' : 'rgba(255,255,255,0.25)',
                        fontWeight: 700,
                        width: 20,
                      }}
                    >
                      {c.done ? '✓' : '○'}
                    </span>
                    <span style={{ color: c.done ? DARK_THEME.textPrimary : DARK_THEME.textMuted }}>{c.label}</span>
                  </div>
                ))}
              </div>
            )}
            {summary.status_text && (
              <p style={{ marginTop: 24, fontSize: 14, color: 'var(--text-2, #cfd8e5)', fontStyle: 'italic', lineHeight: 1.6 }}>
                {summary.status_text}
              </p>
            )}
          </>
        ) : (
          <div style={AI_PLACEHOLDER_STYLE}>AI генерирует основной результат...</div>
        )}
      </ProjectStorySection>

      {/* Кто работал — всегда */}
      <ProjectStorySection title="Кто работал">
        {detail.employees.length > 0 ? (
          detail.employees.map((e, i) => {
            const color = COLORS[i % COLORS.length];
            return (
              <div key={e.employee_id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0' }}>
                <div style={{
                  width: 32, height: 32, borderRadius: '50%', background: color,
                  color: DARK_THEME.textPrimary, display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 12, fontWeight: 700, flexShrink: 0,
                }}>
                  {initials(e.name)}
                </div>
                <div style={{ flex: 1, fontSize: 14, color: i < 2 ? DARK_THEME.textPrimary : 'var(--text-2, #cfd8e5)', fontWeight: i < 2 ? 600 : 400 }}>
                  {e.name}
                </div>
                <div style={{ flex: 2, height: 8, background: 'rgba(255,255,255,0.05)', borderRadius: 4 }}>
                  <div style={{ width: `${(e.hours / empMax) * 100}%`, height: '100%', background: color, borderRadius: 4 }} />
                </div>
                <div style={{ width: 110, textAlign: 'right', fontSize: 14, color: 'var(--text-2, #cfd8e5)' }}>
                  <b style={{ color: DARK_THEME.textPrimary }}>{e.hours}</b> ч ({e.pct}%)
                </div>
              </div>
            );
          })
        ) : (
          <div style={AI_PLACEHOLDER_STYLE}>Нет данных о ворклогах</div>
        )}
      </ProjectStorySection>

      {/* На что ушло время — всегда */}
      <ProjectStorySection title="На что ушло время">
        {(() => {
          const groups = summary?.work_breakdown ?? [];
          const hasAI = groups.length > 0 && detail.issue_hours_by_key.length > 0;
          const hoursMap = hasAI
            ? new Map(detail.issue_hours_by_key.map((r) => [r.key, r.hours]))
            : null;
          const timeSlices = hasAI
            ? (() => {
                const raw = groups.map((g, i) => {
                  const hours = g.child_keys.reduce((acc, k) => acc + (hoursMap!.get(k) ?? 0), 0);
                  return { code: g.label, label: g.label, hours: Math.round(hours), color: AI_PALETTE[i % AI_PALETTE.length], pct: 0 };
                });
                const total = raw.reduce((acc, s) => acc + s.hours, 0);
                return raw.map((s) => ({ ...s, pct: total ? Math.round((s.hours / total) * 100) : 0 }));
              })()
            : detail.categories.map((c) => ({ code: c.code, label: c.label, hours: c.hours, color: c.color || DARK_THEME.textMuted, pct: c.pct }));

          return timeSlices.length > 0 ? (
            <div style={{ display: 'flex', gap: 32, alignItems: 'center', flexWrap: 'wrap' }}>
              <DonutChart
                slices={timeSlices}
                centerValue={`${detail.total_hours} ч`}
                centerLabel={`~${detail.weeks} нед`}
                size={240}
              />
              <div style={{ flex: 1, minWidth: 280 }}>
                {timeSlices.map((s) => (
                  <div key={s.code} style={{ marginBottom: 12 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}>
                      <span style={{ color: 'var(--text-2, #cfd8e5)' }}>{s.label}</span>
                      <span style={{ color: DARK_THEME.textPrimary }}>
                        <b>{s.hours}</b> ч ({s.pct}%)
                      </span>
                    </div>
                    <div style={{ height: 6, background: 'rgba(255,255,255,0.05)', borderRadius: 3, marginTop: 4 }}>
                      <div style={{ width: `${s.pct}%`, height: '100%', background: s.color, borderRadius: 3 }} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div style={AI_PLACEHOLDER_STYLE}>Нет данных о затратах времени</div>
          );
        })()}

        {detail.top_issues.length > 0 && (
          <>
            <h3 style={{ marginTop: 32, fontSize: 18, color: DARK_THEME.textPrimary, fontWeight: 600 }}>Топ-3 задачи</h3>
            {detail.top_issues.slice(0, 3).map((t, i) => (
              <div key={t.key} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', fontSize: 14 }}>
                <span style={{ color: 'var(--text-2, #cfd8e5)' }}>
                  <span style={{ color: DARK_THEME.textMuted, marginRight: 8 }}>{i + 1}.</span>
                  <span style={{ color: DARK_THEME.cyanPrimary, marginRight: 8 }}>{t.key}</span>
                  {t.summary}
                </span>
                <span style={{ color: DARK_THEME.textPrimary }}><b>{t.hours}</b> ч</span>
              </div>
            ))}
          </>
        )}
      </ProjectStorySection>

      {/* Как оценили — всегда */}
      <ProjectStorySection title="Как оценили">
        {hasRatings ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 24 }}>
            {[
              { label: 'Качество', value: detail.rating_quality },
              { label: 'Скорость', value: detail.rating_speed },
              { label: 'Результат', value: detail.rating_result },
            ].map((r, i) => (
              <div key={i} style={{ background: DARK_THEME.cardBg, borderRadius: 8, padding: 24, textAlign: 'center' }}>
                <div style={{ fontSize: 14, color: DARK_THEME.textMuted, marginBottom: 12 }}>{r.label}</div>
                <StarRating value={r.value ?? 0} size={32} />
                <div style={{ fontSize: 22, fontWeight: 700, color: DARK_THEME.textPrimary, marginTop: 8 }}>
                  {r.value ?? '—'} / 5
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div style={AI_PLACEHOLDER_STYLE}>
            Оценка заказчика появится после заполнения полей в Jira
          </div>
        )}
        {summary?.workload_summary && (
          <p style={{ marginTop: 24, fontSize: 14, color: 'var(--text-2, #cfd8e5)', textAlign: 'center', fontStyle: 'italic' }}>
            {summary.workload_summary}
          </p>
        )}
      </ProjectStorySection>
    </div>
  );
};
