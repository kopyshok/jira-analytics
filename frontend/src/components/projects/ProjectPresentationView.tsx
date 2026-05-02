import React from 'react';
import { ProjectHero } from './presentation/ProjectHero';
import { ProjectStorySection } from './presentation/ProjectStorySection';
import { FlowDiagram } from './shared/FlowDiagram';
import { DonutChart } from './shared/DonutChart';
import { StarRating } from './shared/StarRating';
import type { ProjectDetail, ProjectSummary } from '../../types/projects';

interface Props {
  detail: ProjectDetail | undefined;
  summary: ProjectSummary | null | undefined;
}

export const ProjectPresentationView: React.FC<Props> = ({ detail, summary }) => {
  if (!detail) return null;

  const empMax = Math.max(1, detail.employees[0]?.hours ?? 1);

  return (
    <div className="presentation-view" style={{ maxWidth: 960, margin: '0 auto' }}>
      <ProjectHero detail={detail} />

      {summary && summary.goals.length > 0 && (
        <ProjectStorySection title="Что мы делали">
          <ol style={{ paddingLeft: 0, listStyle: 'none', margin: 0 }}>
            {summary.goals.map((g, i) => (
              <li key={i} style={{ display: 'flex', gap: 16, marginBottom: 16, fontSize: 16, color: '#cfd8e5' }}>
                <span style={{ flexShrink: 0, fontSize: 28, fontWeight: 700, color: '#00c9c8', lineHeight: 1, width: 32 }}>{i + 1}</span>
                <span>{g}</span>
              </li>
            ))}
          </ol>
          {detail.description && (
            <p style={{ marginTop: 16, color: '#7e94b8', whiteSpace: 'pre-wrap', fontSize: 14 }}>
              {detail.description.slice(0, 800)}
            </p>
          )}
        </ProjectStorySection>
      )}

      {summary && (
        <ProjectStorySection title="Какой результат">
          <FlowDiagram blocks={summary.result_flow_blocks} />
          {summary.status_text && (
            <p style={{ marginTop: 16, fontSize: 16, color: '#67d68d' }}>{summary.status_text}</p>
          )}
          {summary.result_checklist.length > 0 && (
            <div style={{ marginTop: 16, display: 'flex', gap: 16, flexWrap: 'wrap' }}>
              {summary.result_checklist.map((c, i) => (
                <span key={i} style={{ fontSize: 14, color: c.done ? '#67d68d' : '#7e94b8' }}>
                  {c.done ? '✓' : '○'} {c.label}
                </span>
              ))}
            </div>
          )}
        </ProjectStorySection>
      )}

      {detail.employees.length > 0 && (
        <ProjectStorySection title="Кто работал">
          {detail.employees.map((e, i) => (
            <div key={e.employee_id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '8px 0' }}>
              <div style={{ flex: 1, fontSize: 14, color: i < 2 ? '#fff' : '#cfd8e5', fontWeight: i < 2 ? 600 : 400 }}>
                {e.name}
              </div>
              <div style={{ flex: 2, height: 8, background: 'rgba(255,255,255,0.05)', borderRadius: 4 }}>
                <div style={{ width: `${(e.hours / empMax) * 100}%`, height: '100%', background: i < 2 ? '#00c9c8' : '#7e94b8', borderRadius: 4 }} />
              </div>
              <div style={{ width: 110, textAlign: 'right', fontSize: 14, color: '#cfd8e5' }}>
                <b style={{ color: '#fff' }}>{e.hours}</b> ч ({e.pct}%)
              </div>
            </div>
          ))}
        </ProjectStorySection>
      )}

      {detail.categories.length > 0 && (
        <ProjectStorySection title="На что ушло время">
          <div style={{ display: 'flex', gap: 32, alignItems: 'center', flexWrap: 'wrap' }}>
            <DonutChart
              slices={detail.categories.map(c => ({ code: c.code, label: c.label, hours: c.hours, color: c.color || '#7e94b8' }))}
              centerValue={`${detail.total_hours} ч`}
              centerLabel={`~${detail.weeks} нед`}
              size={240}
            />
            <div style={{ flex: 1, minWidth: 280 }}>
              {detail.categories.map(c => (
                <div key={c.code} style={{ marginBottom: 12 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14 }}>
                    <span style={{ color: '#cfd8e5' }}>{c.label}</span>
                    <span style={{ color: '#fff' }}>
                      <b>{c.hours}</b> ч ({c.pct}%)
                    </span>
                  </div>
                  <div style={{ height: 6, background: 'rgba(255,255,255,0.05)', borderRadius: 3, marginTop: 4 }}>
                    <div style={{ width: `${c.pct}%`, height: '100%', background: c.color || '#7e94b8', borderRadius: 3 }} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          {detail.top_issues.length > 0 && (
            <>
              <h3 style={{ marginTop: 32, fontSize: 18, color: '#fff', fontWeight: 600 }}>Топ-3 задачи</h3>
              {detail.top_issues.slice(0, 3).map((t, i) => (
                <div key={t.key} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', fontSize: 14 }}>
                  <span style={{ color: '#cfd8e5' }}>
                    <span style={{ color: '#7e94b8', marginRight: 8 }}>{i + 1}.</span>
                    <span style={{ color: '#00c9c8', marginRight: 8 }}>{t.key}</span>
                    {t.summary}
                  </span>
                  <span style={{ color: '#fff' }}><b>{t.hours}</b> ч</span>
                </div>
              ))}
            </>
          )}
        </ProjectStorySection>
      )}

      {(detail.rating_quality !== null || detail.rating_speed !== null || detail.rating_result !== null) && (
        <ProjectStorySection title="Как оценили">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 24 }}>
            {[
              { label: 'Качество', value: detail.rating_quality },
              { label: 'Скорость', value: detail.rating_speed },
              { label: 'Результат', value: detail.rating_result },
            ].map((r, i) => (
              <div key={i} style={{ background: '#0f2340', borderRadius: 8, padding: 24, textAlign: 'center' }}>
                <div style={{ fontSize: 14, color: '#7e94b8', marginBottom: 12 }}>{r.label}</div>
                <StarRating value={r.value ?? 0} size={32} />
                <div style={{ fontSize: 22, fontWeight: 700, color: '#fff', marginTop: 8 }}>
                  {r.value ?? '—'} / 5
                </div>
              </div>
            ))}
          </div>
          {summary?.workload_summary && (
            <p style={{ marginTop: 24, fontSize: 14, color: '#cfd8e5', textAlign: 'center', fontStyle: 'italic' }}>
              {summary.workload_summary}
            </p>
          )}
        </ProjectStorySection>
      )}
    </div>
  );
};
