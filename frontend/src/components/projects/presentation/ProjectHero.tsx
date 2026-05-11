import React from 'react';
import { Tag } from 'antd';
import type { ProjectDetail } from '../../../types/projects';
import { useThemeTokens } from '../../../hooks/useThemeTokens';
import { FONTS, type ThemeTokensV2 } from '../../../utils/constants';

export const ProjectHero: React.FC<{ detail: ProjectDetail }> = ({ detail }) => {
  const t = useThemeTokens();

  const periodText = formatPeriod(detail.period_start, detail.period_end);
  const statusTone = statusToneFor(detail.status_category, t);
  const prose = buildProseSummary(detail);

  return (
    <div
      style={{
        padding: '40px 24px 32px',
        borderBottom: `1px solid ${t.border.subtle}`,
      }}
    >
      {/* Project key — small, plain, no uppercase-letter-spaced eyebrow */}
      <div style={{ fontSize: 12, color: t.text.hint, marginBottom: 8, fontFamily: FONTS.mono }}>
        {detail.key}
      </div>

      {/* Title — Fraunces italic, editorial */}
      <h1
        style={{
          margin: '0 0 16px',
          fontFamily: FONTS.display,
          fontStyle: 'italic',
          fontWeight: 500,
          fontSize: 32,
          lineHeight: 1.25,
          color: t.text.primary,
        }}
      >
        {detail.summary}
      </h1>

      {/* Period + status as pill-chips */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        {periodText && (
          <Tag
            style={{
              background: 'transparent',
              border: `1px solid ${t.border.default}`,
              color: t.text.secondary,
              borderRadius: 999,
              padding: '2px 10px',
              fontSize: 12,
              margin: 0,
            }}
          >
            {periodText}
          </Tag>
        )}
        {detail.status && (
          <Tag
            style={{
              background: 'transparent',
              border: `1px solid ${statusTone.border}`,
              color: statusTone.color,
              borderRadius: 999,
              padding: '2px 10px',
              fontSize: 12,
              margin: 0,
            }}
          >
            {detail.status}
          </Tag>
        )}
      </div>

      {/* Prose summary — metrics dissolved into a sentence */}
      <p
        style={{
          margin: 0,
          fontSize: 14,
          lineHeight: 1.6,
          color: t.text.secondary,
          maxWidth: 640,
        }}
      >
        {prose}
      </p>
    </div>
  );
};

function formatPeriod(s: string | null, e: string | null): string | null {
  if (!s && !e) return null;
  const fmt = (iso: string | null) =>
    iso ? new Date(iso).toLocaleDateString('ru', { day: '2-digit', month: '2-digit', year: 'numeric' }) : '—';
  return `${fmt(s)} — ${fmt(e)}`;
}

function statusToneFor(
  category: string | null,
  t: ThemeTokensV2,
): { color: string; border: string } {
  if (category === 'done') return { color: t.status.success, border: t.status.success };
  if (category === 'indeterminate') return { color: t.accent.primary, border: t.accent.primary };
  return { color: t.text.muted, border: t.border.default };
}

function buildProseSummary(d: ProjectDetail): string {
  const parts: string[] = [];
  const people = d.employee_count;
  const weeks = d.weeks;
  const hours = d.total_hours;
  const tasks = d.child_count;

  if (people > 0 && weeks > 0) {
    parts.push(`На проекте ${people} ${pluralizePeople(people)} работали ${weeks} ${pluralizeWeeks(weeks)}`);
  } else if (people > 0) {
    parts.push(`На проекте ${people} ${pluralizePeople(people)}`);
  }

  if (hours > 0) {
    const fmtHours = new Intl.NumberFormat('ru-RU').format(Math.round(hours));
    parts.push(`записали ${fmtHours} ${pluralizeHours(hours)}`);
  }

  if (tasks > 0) {
    parts.push(`в ${tasks} ${pluralizeTasks(tasks)}`);
  }

  if (parts.length === 0) return 'Данных по проекту пока нет.';

  if (parts.length === 1) return parts[0] + '.';

  // [people+weeks] — [hours] в [tasks].
  return parts.length === 3
    ? `${parts[0]} — ${parts[1]} ${parts[2]}.`
    : parts.join(' — ') + '.';
}

function pluralizePeople(n: number): string {
  const last2 = n % 100;
  const last = n % 10;
  if (last2 >= 11 && last2 <= 14) return 'человек';
  if (last === 1) return 'человек';
  if (last >= 2 && last <= 4) return 'человека';
  return 'человек';
}

function pluralizeWeeks(n: number): string {
  const last2 = n % 100;
  const last = n % 10;
  if (last2 >= 11 && last2 <= 14) return 'недель';
  if (last === 1) return 'неделю';
  if (last >= 2 && last <= 4) return 'недели';
  return 'недель';
}

function pluralizeHours(n: number): string {
  const last2 = Math.round(n) % 100;
  const last = Math.round(n) % 10;
  if (last2 >= 11 && last2 <= 14) return 'часов';
  if (last === 1) return 'час';
  if (last >= 2 && last <= 4) return 'часа';
  return 'часов';
}

function pluralizeTasks(n: number): string {
  const last2 = n % 100;
  const last = n % 10;
  if (last2 >= 11 && last2 <= 14) return 'задачах';
  if (last === 1) return 'задаче';
  if (last >= 2 && last <= 4) return 'задачах';
  return 'задачах';
}
