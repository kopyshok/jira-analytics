import React from 'react';
import type { PlanWorkType } from '../../../types/projects';
import { DARK_THEME } from '../../../utils/constants';
import { OVERLOAD_PCT, hoursText, loadTone, loadVerdict } from '../../../utils/projectsView';
import { StageBar } from './StageBar';

const WT_COLOR: Record<string, string> = {
  analyst: '#00c9c8',
  dev: '#378ADD',
  qa: '#EF9F27',
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
  /** Вид скина: крупные числа и полосы «факт / план» вместо колец (классы pjc-kpi-*). */
  compact?: boolean;
}

function pctColor(pct: number | null): string {
  if (pct === null) return DARK_THEME.textMuted;
  if (pct > 110) return '#ff4d4f';
  if (pct >= 70) return '#67d68d';
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
                  stroke={over ? '#ff4d4f' : color}
                  strokeDasharray={RING_CIRC.toFixed(2)}
                  strokeDashoffset={over ? 0 : offset.toFixed(2)}
                  transform="rotate(-90 19 19)" />
        </svg>
        <div style={{
          position: 'absolute', inset: 0, display: 'flex',
          alignItems: 'center', justifyContent: 'center',
          fontSize: 10, fontWeight: 600, color: over ? '#ff4d4f' : DARK_THEME.textPrimary,
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

/** Стадия в виде скина: факт / план, полоса и процент. */
const StageStat: React.FC<{ wt: PlanWorkType }> = ({ wt }) => (
  <div className="pjc-kpi-role">
    <div className="pjc-kpi-role-cap"><span className={`pjc-sw is-${wt.code}`} aria-hidden />{wt.label}</div>
    <div className="pjc-kpi-role-val">{hoursText(wt.fact_hours)} / {hoursText(wt.plan_hours)} ч</div>
    <div className="pjc-kpi-role-bar">
      <StageBar fact={wt.fact_hours} plan={wt.plan_hours} code={wt.code} />
      <span className={wt.pct !== null && wt.pct > OVERLOAD_PCT ? 'pjc-pct is-over' : 'pjc-pct'}>
        {wt.pct === null ? '—' : `${wt.pct}%`}
      </span>
    </div>
  </div>
);

const CompactSummary: React.FC<Omit<Props, 'compact'>> = ({
  countLabel, count, workTypes, externalHours, totalPlan, totalFact, totalPct,
}) => {
  const verdict = loadVerdict(totalPct);
  return (
    <div className="pjc-kpi">
      <div className="pjc-kpi-main">
        {countLabel && count !== undefined && (
          <div>
            <div className="pjc-kpi-cap">Портфель</div>
            <div className="pjc-kpi-val">
              <span className="pjc-kpi-big">{count}</span>
              <span className="pjc-kpi-unit">{countLabel}</span>
            </div>
          </div>
        )}
        <div>
          <div className="pjc-kpi-cap">{totalPlan === null ? 'Факт · план не заведён' : 'Всего факт / план'}</div>
          <div className="pjc-kpi-val">
            <span className="pjc-kpi-big">
              {hoursText(totalFact)}
              {totalPlan !== null && <span className="pjc-kpi-plan"> / {hoursText(totalPlan)}</span>}
            </span>
            <span className="pjc-kpi-unit">ч</span>
          </div>
        </div>
        <div>
          <div className="pjc-kpi-cap">Загрузка</div>
          <div className="pjc-kpi-val is-center">
            <span className="pjc-kpi-big">{totalPct === null ? '—' : `${totalPct}%`}</span>
            {verdict && <span className={`wr-pill is-sm is-${loadTone(totalPct)}`}>{verdict}</span>}
          </div>
        </div>
      </div>
      <div className="pjc-kpi-roles">
        {workTypes.map((wt) => <StageStat key={wt.code} wt={wt} />)}
        <div className="pjc-kpi-role" title="Часы сотрудников не из команды — вне плана и факта">
          <div className="pjc-kpi-role-cap"><span className="pjc-sw is-ext" aria-hidden />Внешние</div>
          <div className="pjc-kpi-role-val">{externalHours > 0 ? `${hoursText(externalHours)} ч` : '—'}</div>
          <div className="pjc-kpi-role-note">без плана</div>
        </div>
      </div>
    </div>
  );
};

const RingsRow: React.FC<Omit<Props, 'compact'>> = ({
  countLabel, count, workTypes, externalHours, totalPlan, totalFact, totalPct,
}) => (
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
        // Тёмная подложка «под тёмную тему»; скины задают свою через переменные.
        background: 'var(--pj-ext-bg, rgba(0,0,0,0.22))',
        border: '1px solid var(--pj-ext-border, rgba(255,255,255,0.04))',
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

export const WorkTypeRings: React.FC<Props> = ({ compact = false, ...props }) =>
  compact ? <CompactSummary {...props} /> : <RingsRow {...props} />;
