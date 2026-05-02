import React from 'react';
import { Tag } from 'antd';
import type { ProjectDetail } from '../../../types/projects';

export const ProjectHero: React.FC<{ detail: ProjectDetail }> = ({ detail }) => (
  <div style={{ padding: '32px 16px', borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
    <div style={{ fontSize: 11, color: '#7e94b8', letterSpacing: 1, textTransform: 'uppercase' }}>
      Проект {detail.key}
    </div>
    <h1 style={{ margin: '8px 0 16px', fontSize: 36, fontWeight: 700, color: '#fff' }}>
      {detail.summary}
    </h1>
    <div style={{ fontSize: 13, color: '#cfd8e5', marginBottom: 20, display: 'flex', alignItems: 'center', gap: 12 }}>
      <span>{formatPeriod(detail.period_start, detail.period_end)}</span>
      <Tag color={statusTagColor(detail.status_category)}>{detail.status}</Tag>
    </div>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
      <BigTile value={detail.total_hours} label="Часов" sub={`~${detail.weeks} нед`} />
      <BigTile value={detail.child_count} label="Задач" />
      <BigTile value={detail.employee_count} label="Участников" />
    </div>
  </div>
);

const BigTile: React.FC<{ value: number | string; label: string; sub?: string }> = ({ value, label, sub }) => (
  <div style={{ background: '#0f2340', borderRadius: 8, padding: '20px 24px', textAlign: 'center' }}>
    <div style={{ fontSize: 36, fontWeight: 700, color: '#fff' }}>{value}</div>
    <div style={{ fontSize: 12, color: '#7e94b8', textTransform: 'uppercase', marginTop: 4 }}>{label}</div>
    {sub && <div style={{ fontSize: 11, color: '#7e94b8', marginTop: 2 }}>{sub}</div>}
  </div>
);

function formatPeriod(s: string | null, e: string | null) {
  if (!s || !e) return 'без периода';
  return `${new Date(s).toLocaleDateString('ru')} — ${new Date(e).toLocaleDateString('ru')}`;
}

function statusTagColor(c: string | null) {
  if (c === 'done') return 'green';
  if (c === 'indeterminate') return 'cyan';
  return 'default';
}
