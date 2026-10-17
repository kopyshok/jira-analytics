import React from 'react';
import type { PlanWorkType } from '../../../types/projects';
import { DARK_THEME } from '../../../utils/constants';

const WT_COLOR: Record<string, string> = {
  analyst: 'var(--pj-stage-analyst, #00c9c8)',
  dev: 'var(--pj-stage-dev, #378ADD)',
  qa: 'var(--pj-stage-qa, #EF9F27)',
};

const RING_CIRC = 2 * Math.PI * 14;

interface Props {
  /** Левая группа: подпись над счётчиком проектов. Нет — группа не рисуется. */
  countLabel?: string;
  count?: number;
  workTypes: PlanWorkType[];
  externalHours: number;
  totalPlan: number | null;
  totalFact: number;
  totalPct: number | null;
  /** rings — кольца (Aurora); bars — колонки «факт / план» с полосой (обложки, итоги — в паспорте). */
  variant?: 'rings' | 'bars';
}

function pctColor(pct: number | null): string {
  if (pct === null) return DARK_THEME.textMuted;
  if (pct > 110) return 'var(--pj-over, #ff4d4f)';
  if (pct >= 70) return 'var(--pj-ok, #67d68d)';
  return DARK_THEME.textPrimary;
}

const Ring: React.FC<{ wt: PlanWorkType }> = ({ wt }) => {
  const over = wt.pct !== null && wt.pct > 110;
  const shown = Math.max(0, Math.min(100, wt.pct ?? 0));
  const offset = RING_CIRC * (1 - shown / 100);
  const color = WT_COLOR[wt.code] ?? DARK_THEME.cyanPrimary;
  return (
    <div
      style={{
        // Ниже 150px кольцо и подписи начинают наезжать друг на друга —
        // пусть лучше плитка переносится на следующую строку.
        flex: '1 1 150px',
        minWidth: 150,
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        padding: '8px 12px',
        background: DARK_THEME.cardBg,
        border: `1px solid ${DARK_THEME.border}`,
        borderRadius: 8,
      }}
    >
      <div style={{ position: 'relative', width: 38, height: 38, flexShrink: 0 }}>
        <svg viewBox="0 0 38 38" width={38} height={38}>
          <circle cx="19" cy="19" r="14" fill="none" strokeWidth="4"
                  stroke="rgba(255,255,255,0.08)" />
          <circle cx="19" cy="19" r="14" fill="none" strokeWidth="4" strokeLinecap="round"
                  // Цвет — свойством стиля: атрибут SVG переменные CSS не понимает.
                  style={{ stroke: over ? 'var(--pj-over, #ff4d4f)' : color }}
                  strokeDasharray={RING_CIRC.toFixed(2)}
                  strokeDashoffset={over ? 0 : offset.toFixed(2)}
                  transform="rotate(-90 19 19)" />
        </svg>
        <div style={{
          position: 'absolute', inset: 0, display: 'flex',
          alignItems: 'center', justifyContent: 'center',
          fontSize: 10, fontWeight: 600, color: over ? 'var(--pj-over, #ff4d4f)' : DARK_THEME.textPrimary,
        }}>
          {wt.pct === null ? '—' : `${wt.pct}%`}
        </div>
      </div>
      <div style={{ minWidth: 0 }}>
        <div style={{
          fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em',
          color, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
        }}>
          {wt.label}
        </div>
        <div style={{ fontSize: 12, color: DARK_THEME.textPrimary, whiteSpace: 'nowrap' }}>
          {Math.round(wt.fact_hours)} / {Math.round(wt.plan_hours)} ч
        </div>
      </div>
    </div>
  );
};

/** Стадия колонкой: метка, «факт / план» крупно, полоса и процент. */
const StageBar: React.FC<{ wt: PlanWorkType }> = ({ wt }) => {
  const over = wt.pct !== null && wt.pct > 110;
  const width = Math.max(0, Math.min(100, wt.pct ?? 0));
  return (
    <div className="pj-stage" data-stage={wt.code} data-over={over ? '' : undefined}>
      <div className="pj-stage-label"><i aria-hidden="true" />{wt.label}</div>
      <div className="pj-stage-hours">{Math.round(wt.fact_hours).toLocaleString('ru-RU')} / {Math.round(wt.plan_hours).toLocaleString('ru-RU')} ч</div>
      <div className="pj-stage-bar">
        <span className="pj-stage-track"><span style={{ width: `${width}%` }} /></span>
        <b className="pj-stage-pct" data-level={wt.pct === null ? 'none' : over ? 'over' : wt.pct >= 70 ? 'ok' : 'low'}>
          {wt.pct === null ? '—' : `${wt.pct}%`}
        </b>
      </div>
    </div>
  );
};

export const WorkTypeRings: React.FC<Props> = ({
  countLabel, count, workTypes, externalHours, totalPlan, totalFact, totalPct, variant = 'rings',
}) => variant === 'bars' ? (
  <div className="pj-stages">
    {workTypes.map((wt) => <StageBar key={wt.code} wt={wt} />)}
    <div className="pj-stage" data-stage="external" title="Часы сотрудников не из команды — вне плана и факта">
      <div className="pj-stage-label"><i aria-hidden="true" />Внешние</div>
      <div className="pj-stage-hours">{Math.round(externalHours).toLocaleString('ru-RU')} ч</div>
      <div className="pj-stage-note">без плана</div>
    </div>
  </div>
) : (
  <div style={{ display: 'flex', alignItems: 'stretch', gap: 10, flexWrap: 'wrap' }}>
    <div style={{ display: 'flex', alignItems: 'center', gap: 20, paddingRight: 8, flex: '0 0 auto' }}>
      {countLabel && count !== undefined && (
        <div>
          <div style={{ fontSize: 22, fontWeight: 700, color: DARK_THEME.textPrimary, lineHeight: 1.1 }}>
            {count}
          </div>
          <div style={{ fontSize: 11, color: DARK_THEME.textMuted }}>{countLabel}</div>
        </div>
      )}
      <div>
        <div style={{ fontSize: 22, fontWeight: 700, color: DARK_THEME.textPrimary, lineHeight: 1.1 }}>
          {Math.round(totalFact)} / {totalPlan === null ? '—' : Math.round(totalPlan)} ч
        </div>
        <div style={{ fontSize: 11, color: DARK_THEME.textMuted }}>
          {totalPlan === null ? 'план не заведён' : 'всего факт / план'}
        </div>
      </div>
      <div>
        <div style={{ fontSize: 22, fontWeight: 700, color: pctColor(totalPct), lineHeight: 1.1 }}>
          {totalPct === null ? '—' : `${totalPct}%`}
        </div>
        <div style={{ fontSize: 11, color: DARK_THEME.textMuted }}>загрузка</div>
      </div>
    </div>

    {workTypes.map((wt) => <Ring key={wt.code} wt={wt} />)}

    <div
      title={externalHours > 0 ? 'Часы сотрудников не из команды — вне плана и факта' : undefined}
      style={{
        flex: '0 0 96px', padding: '8px 10px', borderRadius: 8,
        background: 'var(--pj-ext-bg, rgba(0,0,0,0.22))',
        border: '1px solid var(--pj-chip-bg, rgba(255,255,255,0.04))',
        display: 'flex', flexDirection: 'column', justifyContent: 'center',
      }}
    >
      {externalHours > 0 && (
        <>
          <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.06em', color: DARK_THEME.textMuted }}>
            Внешние
          </div>
          <div style={{ fontSize: 12, color: DARK_THEME.textMuted }}>
            {Math.round(externalHours)} ч
          </div>
        </>
      )}
    </div>
  </div>
);
