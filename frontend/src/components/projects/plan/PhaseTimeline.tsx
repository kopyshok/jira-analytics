import React from 'react';
import { Tooltip, Empty } from 'antd';
import type { PlanTimeline } from '../../../types/projects';
import { DARK_THEME, MONTH_NAMES } from '../../../utils/constants';

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
}

export const PhaseTimeline: React.FC<Props> = ({ timeline, mode, onRowClick, maxHeight }) => {
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
