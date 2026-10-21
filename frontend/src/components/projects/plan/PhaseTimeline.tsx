import React from 'react';
import { Tooltip, Empty } from 'antd';
import type { PlanTimeline } from '../../../types/projects';
import { DARK_THEME, MONTH_NAMES } from '../../../utils/constants';
import { timelineScale } from '../../../utils/projectsView';

const PHASE_COLOR: Record<string, string> = {
  analyst: '#00c9c8',
  cons: '#00c9c8',
  dev: '#378ADD',
  qa: '#EF9F27',
  opo: '#7F77DD',
};

const LANE_H = 20;

function toTime(iso: string): number {
  return new Date(iso.slice(0, 10)).getTime();
}

/** Начало месяца, в который попадает дата. */
function monthFloor(iso: string): Date {
  const d = new Date(iso.slice(0, 10));
  return new Date(d.getFullYear(), d.getMonth(), 1);
}

/** Начало месяца, следующего за датой. */
function monthCeil(iso: string): Date {
  const d = new Date(iso.slice(0, 10));
  return new Date(d.getFullYear(), d.getMonth() + 1, 1);
}

function monthLabels(start: Date, end: Date): string[] {
  const out: string[] = [];
  const cur = new Date(start.getFullYear(), start.getMonth(), 1);
  while (cur.getTime() < end.getTime()) {
    out.push((MONTH_NAMES[cur.getMonth() + 1] ?? '').slice(0, 3));
    cur.setMonth(cur.getMonth() + 1);
  }
  return out;
}

interface Props {
  timeline: PlanTimeline;
  /** 'by-phase' — подпись строки = название фазы (один проект).
   *  'by-project' — подпись строки = ключ и название проекта. */
  mode: 'by-phase' | 'by-project';
  onRowClick?: (key: string) => void;
  /** Высота области строк; всё, что выше — прокручивается внутри блока.
   *  Нужна портфелю: строк там столько же, сколько проектов у выбранных команд. */
  maxHeight?: number | string;
  /** Вид скина: заголовок с легендой, затенение вне квартала, своя прокрутка (классы pjc-tl-*). */
  compact?: boolean;
  /** Заголовок блока в виде скина. */
  title?: string;
}

const LEGEND: Array<[string, string]> = [
  ['analyst', 'Анализ'], ['dev', 'Разработка'], ['qa', 'Тестирование'], ['opo', 'ОПЭ'],
];

/** '2026-10-01' → '01.10.2026' — подсказка полосы. */
function fullDate(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split('-');
  return `${d}.${m}.${y}`;
}

/**
 * Таймлайн в виде скина: заголовок с легендой, подписи месяцев по числу дней,
 * затенение вне квартала, линия «сегодня», строки 30 px со своей прокруткой
 * (классы pjc-tl-*). Фазу «Консультация» красим как анализ — как и в Aurora.
 */
const CompactTimeline: React.FC<Omit<Props, 'compact' | 'maxHeight'>> = ({ timeline, mode, onRowClick, title }) => {
  const scale = timelineScale(timeline);
  const now = new Date();
  const todayText = `${String(now.getDate()).padStart(2, '0')}.${String(now.getMonth() + 1).padStart(2, '0')}`;
  const rows = mode === 'by-phase'
    ? timeline.rows.flatMap((r) => r.bars.map((b) => ({ key: r.key, title: b.label, bars: [b], phaseRow: true })))
    : timeline.rows.map((r) => ({ key: r.key, title: r.title ?? '', bars: r.bars, phaseRow: false }));
  // В легенде — только фазы, которые есть на шкале (консультация красится как анализ).
  const present = new Set(rows.flatMap((r) => r.bars.map((b) => (b.phase === 'cons' ? 'analyst' : b.phase))));
  const legend = LEGEND.filter(([code]) => present.has(code));

  return (
    <div className="pjc-tl">
      <div className="pjc-tl-head">
        {title && <h2 className="rpc-card-title">{title}</h2>}
        <div className="pjc-tl-legend">
          {legend.map(([code, label]) => (
            <span key={code}><span className={`pjc-tl-sw is-${code}`} aria-hidden />{label}</span>
          ))}
          <span><span className="pjc-tl-sw is-shade" aria-hidden />Затенено — вне квартала</span>
          {scale?.todayLeft != null && <span><span className="pjc-tl-sw is-today" aria-hidden />сегодня {todayText}</span>}
        </div>
      </div>
      {!scale || rows.length === 0 ? (
        <Empty className="pjc-tl-empty" description="Нет плановых дат" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      ) : (
        <div className="pjc-tl-scroll">
          <div className={`pjc-tl-grid${mode === 'by-phase' ? ' is-phases' : ''}`}>
            <div className="pjc-tl-axis-row">
              <div className="pjc-tl-corner" />
              <div className="pjc-tl-axis">
                {scale.months.map((m, i) => (
                  <span
                    key={i}
                    className={`pjc-tl-month${m.inQuarter ? ' is-in' : ''}`}
                    style={{ left: `${m.left}%`, width: `${m.width}%` }}
                  >
                    {m.label}
                  </span>
                ))}
                {scale.todayLeft !== null && (
                  <span className="pjc-tl-today" style={{ left: `${scale.todayLeft}%` }} />
                )}
              </div>
            </div>
            <div className="pjc-tl-body">
              <div className="pjc-tl-layer" aria-hidden>
                <span className="pjc-tl-shade" style={{ left: 0, width: `${scale.quarterLeft}%` }} />
                <span className="pjc-tl-shade" style={{ left: `${scale.quarterRight}%`, right: 0 }} />
                {scale.months.slice(1).map((m, i) => (
                  <span key={i} className="pjc-tl-line" style={{ left: `${m.left}%` }} />
                ))}
              </div>
              {/* «Сегодня» — поверх полос, затенение и сетка — под ними. */}
              {scale.todayLeft !== null && (
                <div className="pjc-tl-layer is-top" aria-hidden>
                  <span className="pjc-tl-today" style={{ left: `${scale.todayLeft}%` }} />
                </div>
              )}
              {rows.map((row, ri) => (
                <div key={`${row.key ?? ''}-${ri}`} className="pjc-tl-row">
                  <div className="pjc-tl-label" title={row.phaseRow ? row.title : `${row.key ?? ''} · ${row.title}`}>
                    {row.phaseRow ? (
                      <span className="pjc-tl-phase">{row.title}</span>
                    ) : (
                      <>
                        {row.key && (onRowClick ? (
                          <button type="button" className="pjc-tl-key" onClick={() => onRowClick(row.key!)}>
                            {row.key}
                          </button>
                        ) : <span className="pjc-tl-key">{row.key}</span>)}
                        {/* Как в Aurora, щелчок по названию тоже открывает проект; с клавиатуры — кнопка ключа. */}
                        <span
                          className={`pjc-tl-title${onRowClick && row.key ? ' is-link' : ''}`}
                          onClick={onRowClick && row.key ? () => onRowClick(row.key!) : undefined}
                        >
                          {row.title}
                        </span>
                      </>
                    )}
                  </div>
                  <div className="pjc-tl-lane">
                    {row.bars.map((b, bi) => {
                      const { left, width } = scale.bar(b.start_date, b.end_date);
                      return (
                        <Tooltip
                          key={bi}
                          mouseEnterDelay={0.2}
                          title={`${b.label}: ${fullDate(b.start_date)} — ${fullDate(b.end_date)}`}
                        >
                          <span
                            className={`pjc-tl-bar is-${b.phase}`}
                            style={{ left: `${left}%`, width: `${width}%` }}
                          />
                        </Tooltip>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export const PhaseTimeline: React.FC<Props> = ({ timeline, mode, onRowClick, maxHeight, compact = false, title }) => {
  if (compact) return <CompactTimeline timeline={timeline} mode={mode} onRowClick={onRowClick} title={title} />;
  if (!timeline.start || !timeline.end || timeline.rows.length === 0) {
    return (
      <Empty
        description={<span style={{ color: DARK_THEME.textMuted }}>Нет плановых дат</span>}
        image={Empty.PRESENTED_IMAGE_SIMPLE}
      />
    );
  }

  const scaleStart = monthFloor(timeline.start);
  const scaleEnd = monthCeil(timeline.end);
  const s0 = scaleStart.getTime();
  const span = scaleEnd.getTime() - s0 || 1;
  const pos = (t: number) => ((t - s0) / span) * 100;

  // Подпись проекта — ключ плюс длинное название, ей нужно вдвое больше места
  // и перенос на вторую строку. Названия фаз короткие, там ширины хватает.
  const labelW = mode === 'by-project' ? 340 : 190;

  const labels = monthLabels(scaleStart, scaleEnd);
  const gridlines = labels.map((_, i) => (i / labels.length) * 100).slice(1);

  // Затенение квартала обрезается по границам строки: даты квартала приходят
  // из фильтра списка и могут не пересекаться с плановыми датами проекта.
  const qLeft = Math.max(0, Math.min(100, pos(toTime(timeline.quarter_start))));
  const qRight = Math.max(0, Math.min(100, pos(toTime(timeline.quarter_end))));

  const nowTime = new Date().getTime();
  const nowLeft = nowTime >= s0 && nowTime <= scaleEnd.getTime() ? pos(nowTime) : null;

  // 'by-phase': каждая полоса становится своей строкой, подпись — название фазы.
  const rows = mode === 'by-phase'
    ? timeline.rows.flatMap((r) =>
        r.bars.map((b) => ({ key: r.key, label: b.label, bars: [b] })))
    : timeline.rows.map((r) => ({
        key: r.key,
        label: `${r.key ?? ''} · ${r.title ?? ''}`.trim(),
        bars: r.bars,
      }));

  return (
    <div>
      <div style={{
        display: 'grid', gridTemplateColumns: `${labelW}px 1fr`, gap: 8, marginBottom: 4,
      }}>
        <div />
        <div style={{ display: 'grid', gridTemplateColumns: `repeat(${labels.length}, 1fr)` }}>
          {labels.map((m, i) => (
            <div key={i} style={{
              fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.08em',
              color: DARK_THEME.textMuted, textAlign: 'center',
            }}>{m}</div>
          ))}
        </div>
      </div>

      <div style={maxHeight ? { maxHeight, overflowY: 'auto', paddingRight: 4 } : undefined}>
      {rows.map((row, ri) => (
        <div
          key={`${row.key ?? ''}-${ri}`}
          style={{
            display: 'grid', gridTemplateColumns: `${labelW}px 1fr`,
            gap: 8, marginBottom: 3, alignItems: 'center',
          }}
        >
          <div
            role={onRowClick && row.key ? 'button' : undefined}
            tabIndex={onRowClick && row.key ? 0 : undefined}
            onClick={onRowClick && row.key ? () => onRowClick(row.key!) : undefined}
            onKeyDown={onRowClick && row.key ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onRowClick(row.key!); }
            } : undefined}
            title={row.label}
            style={{
              fontSize: 11, lineHeight: 1.3, color: DARK_THEME.textPrimary,
              // Две строки максимум: третья растянула бы строку таймлайна и
              // полосы разъехались бы по вертикали.
              display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
              overflow: 'hidden', overflowWrap: 'anywhere',
              cursor: onRowClick && row.key ? 'pointer' : 'default',
            }}
          >
            {row.label}
          </div>
          <div style={{
            position: 'relative', height: LANE_H + 6,
            background: 'rgba(255,255,255,0.02)', borderRadius: 4,
            overflow: 'hidden',
          }}>
            <div style={{
              position: 'absolute', top: 0, bottom: 0,
              left: `${qLeft}%`, width: `${Math.max(0, qRight - qLeft)}%`,
              background: 'rgba(255,255,255,0.035)',
              borderLeft: '1px dashed rgba(255,255,255,0.14)',
              borderRight: '1px dashed rgba(255,255,255,0.14)',
            }} />
            {gridlines.map((g, i) => (
              <div key={i} style={{
                position: 'absolute', top: 0, bottom: 0, left: `${g}%`,
                width: 1, background: 'rgba(255,255,255,0.05)',
              }} />
            ))}
            {row.bars.map((b, bi) => {
              const left = pos(toTime(b.start_date));
              const width = Math.max(1.5, pos(toTime(b.end_date)) - left);
              return (
                <Tooltip
                  key={bi}
                  mouseEnterDelay={0.2}
                  title={`${b.label}: ${b.start_date} — ${b.end_date}`}
                >
                  <div style={{
                    position: 'absolute', top: 3, height: LANE_H,
                    left: `${left}%`, width: `${width}%`,
                    background: PHASE_COLOR[b.phase] ?? DARK_THEME.cyanPrimary,
                    borderRadius: 4, color: '#0d1c33', fontSize: 10, lineHeight: `${LANE_H}px`,
                    padding: '0 5px', overflow: 'hidden', whiteSpace: 'nowrap',
                  }}>
                    {width > 8 ? b.label : ''}
                  </div>
                </Tooltip>
              );
            })}
            {nowLeft !== null && (
              <div style={{
                position: 'absolute', top: 0, bottom: 0, left: `${nowLeft}%`,
                width: 2, background: DARK_THEME.cyanPrimary,
              }} />
            )}
          </div>
        </div>
      ))}
      </div>

      <div style={{
        display: 'flex', gap: 14, flexWrap: 'wrap', marginTop: 8,
        fontSize: 11, color: DARK_THEME.textMuted,
      }}>
        {[['analyst', 'Анализ'], ['dev', 'Разработка'], ['qa', 'Тестирование'], ['opo', 'ОПЭ']].map(
          ([code, label]) => (
            <span key={code} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{
                width: 10, height: 10, borderRadius: 2, background: PHASE_COLOR[code],
              }} />
              {label}
            </span>
          ),
        )}
        <span style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={{ width: 2, height: 11, background: DARK_THEME.cyanPrimary }} />
          сегодня
        </span>
        <span>Затенено — границы квартала</span>
      </div>
    </div>
  );
};
