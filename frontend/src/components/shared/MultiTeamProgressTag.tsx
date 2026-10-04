import type { CSSProperties } from 'react';
import { Tag, Tooltip } from 'antd';
import type { MultiTeamProgress } from '../../types/api';
import { progressTone, teamTakeLine, type ProgressTone } from '../../utils/multiTeamProgress';

// Цвета — токены темы: в светлой и тёмной теме свои значения.
const TONE_STYLE: Record<ProgressTone, CSSProperties> = {
  none: { color: 'var(--text-muted, #8c8c8c)' },
  neutral: {},
  alert: {
    color: '#1f1600',
    background: 'var(--warn, #fbbf24)',
    borderColor: 'var(--warn, #fbbf24)',
    fontWeight: 600,
  },
  done: {
    color: 'var(--good, #34d399)',
    background: 'color-mix(in srgb, var(--good, #34d399) 14%, transparent)',
    borderColor: 'color-mix(in srgb, var(--good, #34d399) 45%, transparent)',
  },
};

const COMPACT: CSSProperties = { fontSize: 10, padding: '0 4px', lineHeight: '18px' };

/** Плашка «в работе у K из N» мультикомандной RFA; в подсказке — все команды со статусами. */
export default function MultiTeamProgressTag({
  progress,
  compact = false,
}: {
  progress: MultiTeamProgress;
  /** Мелкая — для строки сценария, рядом с такими же метками. */
  compact?: boolean;
}) {
  const tone = progressTone(progress);
  return (
    <Tooltip
      title={
        <div>
          <div style={{ fontWeight: 600, marginBottom: 4 }}>
            В работе у {progress.taken} из {progress.total} команд
          </div>
          {progress.teams.map((t) => (
            <div key={t.team}>{teamTakeLine(t)}</div>
          ))}
        </div>
      }
    >
      <Tag
        // Строка сценария переключает включение по щелчку — плашка его не ловит.
        onClick={(e) => e.stopPropagation()}
        style={{ marginInlineEnd: 0, ...(compact ? COMPACT : null), ...TONE_STYLE[tone] }}
      >
        в работе у {progress.taken} из {progress.total}
      </Tag>
    </Tooltip>
  );
}
