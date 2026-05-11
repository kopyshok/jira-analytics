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
}

export const ProjectListCard: React.FC<Props> = ({ item, selected, onClick }) => {
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
                background: 'rgba(126,148,184,0.12)',
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
