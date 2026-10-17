import React from 'react';
import type { ProjectListItem } from '../../types/projects';
import { StarRating } from './shared/StarRating';
import { DARK_THEME } from '../../utils/constants';

const STATUS_CATEGORY_COLOR: Record<string, string> = {
  done: '#67d68d',
  indeterminate: DARK_THEME.cyanPrimary,
  new: DARK_THEME.textMuted,
};

const STATUS_CATEGORY_LABEL: Record<string, string> = {
  done: 'Готов',
  indeterminate: 'В работе',
  new: 'Новый',
};

const CATEGORY_LABEL: Record<string, string> = {
  quarterly_tasks: 'Квартальные',
  archive_target: 'Архив',
};

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('ru-RU', { month: 'short', year: '2-digit' });
}

interface Props {
  item: ProjectListItem;
  selected: boolean;
  onClick: () => void;
  /** card — плиткой (Aurora); line — строкой списка с линией (обложки). */
  variant?: 'card' | 'line';
}

/** Число задач со склонением: «1 задача», «3 задачи», «5 задач». */
function tasksLabel(n: number): string {
  const m10 = n % 10;
  const m100 = n % 100;
  if (m10 === 1 && m100 !== 11) return `${n} задача`;
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return `${n} задачи`;
  return `${n} задач`;
}

export const ProjectListCard: React.FC<Props> = ({ item, selected, onClick, variant = 'card' }) => {
  const statusColor = item.status_category
    ? (STATUS_CATEGORY_COLOR[item.status_category] ?? DARK_THEME.textMuted)
    : DARK_THEME.textMuted;

  const avgRating =
    item.rating_quality != null || item.rating_speed != null || item.rating_result != null
      ? Math.round(
          ((item.rating_quality ?? 0) + (item.rating_speed ?? 0) + (item.rating_result ?? 0)) /
            [item.rating_quality, item.rating_speed, item.rating_result].filter((v) => v != null)
              .length,
        )
      : null;

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onClick();
    }
  };

  if (variant === 'line') {
    const rating = [item.rating_quality, item.rating_speed, item.rating_result].filter((v): v is number => v != null);
    const avgExact = rating.length ? rating.reduce((a, b) => a + b, 0) / rating.length : null;
    return (
      <div
        data-testid="project-card"
        role="button"
        tabIndex={0}
        aria-pressed={selected}
        onClick={onClick}
        onKeyDown={handleKeyDown}
        className={`pj-line${selected ? ' is-selected' : ''}`}
        data-status={item.status_category ?? 'none'}
      >
        <span className="pj-line-mark" aria-hidden="true" />
        <span className="pj-line-body">
          <span className="pj-line-top">
            <span>
              <b>{item.key}</b>{' '}
              {item.status_category && (
                <span className="pj-line-status">
                  {STATUS_CATEGORY_LABEL[item.status_category] ?? item.status_category}
                </span>
              )}
            </span>
            <b className="pj-line-hours">{Math.round(item.total_hours)} ч</b>
          </span>
          <span className="pj-line-title">{item.summary}</span>
          <span className="pj-line-meta">
            {formatDate(item.period_start)} – {formatDate(item.period_end)} · {tasksLabel(item.child_count)}
            {' · '}{item.employee_count} участн. · {CATEGORY_LABEL[item.category] ?? item.category}
          </span>
          {avgRating != null && avgExact != null && (
            <span className="pj-line-rating">
              <StarRating value={avgRating} size={12} />
              <span>{avgExact.toLocaleString('ru-RU', { maximumFractionDigits: 1 })} из 5</span>
            </span>
          )}
        </span>
      </div>
    );
  }

  return (
    <div
      data-testid="project-card"
      role="button"
      tabIndex={0}
      onClick={onClick}
      onKeyDown={handleKeyDown}
      style={{
        display: 'flex',
        alignItems: 'stretch',
        background: selected ? DARK_THEME.darkAccent : DARK_THEME.cardBg,
        border: `1px solid ${selected ? DARK_THEME.cyanPrimary : DARK_THEME.border}`,
        borderRadius: 8,
        cursor: 'pointer',
        marginBottom: 6,
        overflow: 'hidden',
        transition: 'border-color 0.15s',
        minHeight: 80,
      }}
    >
      {/* Цветная полоса слева */}
      <div style={{ width: 4, flexShrink: 0, background: statusColor }} />

      {/* Основное содержимое */}
      <div style={{ flex: 1, padding: '10px 12px', minWidth: 0 }}>
        {/* Строка 1: ключ + название */}
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginBottom: 6 }}>
          <span style={{ fontSize: 11, color: DARK_THEME.textMuted, flexShrink: 0 }}>{item.key}</span>
          <span
            style={{
              fontSize: 13,
              fontWeight: 600,
              color: DARK_THEME.textPrimary,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {item.summary}
          </span>
        </div>

        {/* Строка 2: метки */}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <MetaTag icon="📅">{`${formatDate(item.period_start)} – ${formatDate(item.period_end)}`}</MetaTag>
          <MetaTag icon="⏱">{`${Math.round(item.total_hours)} ч`}</MetaTag>
          <MetaTag icon="📋">{`${item.child_count} задач`}</MetaTag>
          <MetaTag icon="👥">{`${item.employee_count} участн.`}</MetaTag>
        </div>

        {/* Строка 3: статус-pill + звёзды */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginTop: 6,
          }}
        >
          <div style={{ display: 'flex', gap: 6 }}>
            {item.status_category && (
              <span
                style={{
                  fontSize: 11,
                  padding: '1px 8px',
                  borderRadius: 10,
                  background: `${statusColor}22`,
                  color: statusColor,
                  border: `1px solid ${statusColor}55`,
                }}
              >
                {STATUS_CATEGORY_LABEL[item.status_category] ?? item.status_category}
              </span>
            )}
            <span
              style={{
                fontSize: 11,
                padding: '1px 8px',
                borderRadius: 10,
                background: 'var(--pj-cat-bg, rgba(126,148,184,0.12))',
                color: DARK_THEME.textMuted,
              }}
            >
              {CATEGORY_LABEL[item.category] ?? item.category}
            </span>
          </div>
          {avgRating != null && <StarRating value={avgRating} size={13} />}
        </div>
      </div>
    </div>
  );
};

const MetaTag: React.FC<{ icon: string; children: React.ReactNode }> = ({ icon, children }) => (
  <span style={{ fontSize: 11, color: DARK_THEME.textMuted, display: 'flex', alignItems: 'center', gap: 3 }}>
    <span style={{ fontSize: 10 }}>{icon}</span>
    {children}
  </span>
);
