import React from 'react';
import { Table, Tag, Tooltip } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { PlanChild, PlanWorkType, PortfolioProject, PlanTimeline } from '../../../types/projects';
import { statusTagColor } from '../../../utils/status';
import { DARK_THEME } from '../../../utils/constants';

const WT_COLOR: Record<string, string> = {
  analyst: '#00c9c8',
  dev: '#378ADD',
  qa: '#EF9F27',
};
const OVER = '#ff4d4f';
/** Выше этого процента загрузка считается перегрузом — та же граница, что в кольцах и Capacity. */
const OVERLOAD_PCT = 110;

const STAGES: Array<{ code: string; label: string }> = [
  { code: 'analyst', label: 'Анализ' },
  { code: 'dev', label: 'Разработка' },
  { code: 'qa', label: 'Тестирование' },
];

function pctColor(pct: number | null): string {
  if (pct === null) return DARK_THEME.textMuted;
  if (pct > OVERLOAD_PCT) return OVER;
  if (pct >= 70) return '#67d68d';
  return DARK_THEME.textPrimary;
}

/** '2026-07-01' → '01.07'. Пустая строка, если даты нет. */
function shortDate(iso: string | undefined): string {
  if (!iso) return '';
  const [, m, d] = iso.split('-');
  return m && d ? `${d}.${m}` : '';
}

/** Границы работ по каждому проекту — из полос таймлайна, отдельного запроса не нужно. */
function datesByKey(timeline: PlanTimeline): Record<string, { start: string; end: string }> {
  const out: Record<string, { start: string; end: string }> = {};
  timeline.rows.forEach((row) => {
    if (!row.key || row.bars.length === 0) return;
    const starts = row.bars.map((b) => b.start_date).sort();
    const ends = row.bars.map((b) => b.end_date).sort();
    out[row.key] = { start: starts[0], end: ends[ends.length - 1] };
  });
  return out;
}

const StageCell: React.FC<{ wt: PlanWorkType | undefined }> = ({ wt }) => {
  if (!wt) return <span style={{ color: DARK_THEME.textMuted }}>—</span>;
  const over = wt.pct !== null && wt.pct > OVERLOAD_PCT;
  const color = over ? OVER : (WT_COLOR[wt.code] ?? DARK_THEME.cyanPrimary);
  const width = wt.pct === null ? 0 : Math.min(100, Math.max(0, wt.pct));
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
      <div style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
        <span style={{ color: DARK_THEME.textMuted }}>
          {Math.round(wt.fact_hours)} / {Math.round(wt.plan_hours)} ч
        </span>
        <span style={{ color, fontWeight: 600, marginLeft: 8 }}>
          {wt.pct === null ? '—' : `${wt.pct}%`}
        </span>
      </div>
      <div style={{ width: '100%', minWidth: 64, height: 5, borderRadius: 3, background: 'rgba(255,255,255,0.08)' }}>
        <div style={{ width: `${width}%`, height: '100%', borderRadius: 3, background: color }} />
      </div>
    </div>
  );
};

/** Подзадачи проекта — раскрываются под строкой, как на рабочих столах аналитиков. */
const ChildrenList: React.FC<{ items: PlanChild[] }> = ({ items }) => (
  <div style={{ padding: '4px 0 4px 24px', display: 'flex', flexDirection: 'column', gap: 2 }}>
    {items.map((c) => (
      <div
        key={c.key}
        style={{
          display: 'flex', alignItems: 'center', gap: 10, padding: '4px 8px',
          borderRadius: 4, fontSize: 12,
        }}
      >
        <a
          href={c.jira_url ?? undefined}
          target="_blank"
          rel="noreferrer"
          onClick={(e) => e.stopPropagation()}
          style={{ color: DARK_THEME.cyanPrimary, whiteSpace: 'nowrap' }}
        >
          {c.key}
        </a>
        <span style={{
          flex: 1, minWidth: 0, color: DARK_THEME.textPrimary,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {c.title ?? c.key}
        </span>
        {c.status && (
          <Tag
            color={statusTagColor(c.status, c.status_category)}
            style={{ margin: 0, fontSize: 11, lineHeight: '16px' }}
          >
            {c.status}
          </Tag>
        )}
        <span style={{ color: DARK_THEME.textMuted, whiteSpace: 'nowrap', minWidth: 48, textAlign: 'right' }}>
          {Math.round(c.hours)} ч
        </span>
      </div>
    ))}
  </div>
);

interface Props {
  projects: PortfolioProject[];
  timeline: PlanTimeline;
  /** Итоги портфеля — строка «Итого» под таблицей. */
  totals: {
    workTypes: PlanWorkType[];
    externalHours: number;
    totalPlan: number | null;
    totalFact: number;
    totalPct: number | null;
  };
  onRowClick: (key: string) => void;
  /** Высота области строк; всё, что выше — прокручивается внутри таблицы. */
  maxHeight?: number | string;
}

export const PortfolioProjectsTable: React.FC<Props> = ({ projects, timeline, totals, onRowClick, maxHeight }) => {
  const dates = React.useMemo(() => datesByKey(timeline), [timeline]);
  const hasExternal = projects.some((p) => p.external_hours > 0) || totals.externalHours > 0;

  const stageColumns: ColumnsType<PortfolioProject> = STAGES.map((s) => ({
    title: s.label,
    key: s.code,
    align: 'right' as const,
    width: 132,
    sorter: (a, b) => (findWt(a, s.code)?.pct ?? -1) - (findWt(b, s.code)?.pct ?? -1),
    render: (_: unknown, p: PortfolioProject) => <StageCell wt={findWt(p, s.code)} />,
  }));

  const columns: ColumnsType<PortfolioProject> = [
    {
      title: 'Проект',
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
      sorter: (a, b) => (a.title ?? '').localeCompare(b.title ?? ''),
      render: (_: unknown, p: PortfolioProject) => {
        const d = dates[p.key];
        return (
          <div style={{ minWidth: 0 }}>
            <div style={{
              color: DARK_THEME.textPrimary, fontWeight: 500,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {p.title ?? p.key}
            </div>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap', marginTop: 3 }}>
              {p.priority !== null && (
                <Tag style={{ margin: 0, fontSize: 11, lineHeight: '16px' }}>P{p.priority}</Tag>
              )}
              <span style={{ fontSize: 11, color: DARK_THEME.cyanPrimary }}>{p.key}</span>
              {d && (
                <span style={{ fontSize: 11, color: DARK_THEME.textMuted }}>
                  {shortDate(d.start)} – {shortDate(d.end)}
                </span>
              )}
              {p.status && (
                <Tag
                  color={statusTagColor(p.status, p.status_category)}
                  style={{ margin: 0, fontSize: 11, lineHeight: '16px' }}
                >
                  {p.status}
                </Tag>
              )}
            </div>
          </div>
        );
      },
    },
    {
      title: 'Факт / План',
      key: 'hours',
      align: 'right',
      width: 118,
      sorter: (a, b) => a.total_fact - b.total_fact,
      render: (_: unknown, p: PortfolioProject) => (
        <span style={{ color: DARK_THEME.textPrimary, whiteSpace: 'nowrap' }}>
          {Math.round(p.total_fact)} / {p.total_plan === null ? '—' : Math.round(p.total_plan)} ч
        </span>
      ),
    },
    {
      title: 'Загрузка',
      key: 'pct',
      align: 'right',
      width: 92,
      defaultSortOrder: 'descend',
      sorter: (a, b) => (a.total_pct ?? -1) - (b.total_pct ?? -1),
      render: (_: unknown, p: PortfolioProject) => (
        <span style={{ color: pctColor(p.total_pct), fontWeight: 600 }}>
          {p.total_pct === null ? '—' : `${p.total_pct}%`}
        </span>
      ),
    },
    ...stageColumns,
  ];

  if (hasExternal) {
    columns.push({
      title: 'Внешние',
      key: 'external',
      align: 'right',
      width: 88,
      sorter: (a, b) => a.external_hours - b.external_hours,
      render: (_: unknown, p: PortfolioProject) => (
        <Tooltip title="Часы сотрудников не из команды проекта — вне плана и факта">
          <span style={{ color: DARK_THEME.textMuted }}>
            {p.external_hours > 0 ? `${Math.round(p.external_hours)} ч` : '—'}
          </span>
        </Tooltip>
      ),
    });
  }

  return (
    <Table<PortfolioProject>
      data-testid="portfolio-projects-table"
      rowKey="key"
      size="small"
      columns={columns}
      dataSource={projects}
      pagination={false}
      // Своя вертикальная прокрутка: шапка и итоги остаются на месте, а список
      // не растягивается на всю длину при нескольких выбранных командах.
      scroll={{ x: 'max-content', y: maxHeight }}
      expandable={{
        // Иначе AntD принимает поле children за вложенные строки-дерево и
        // рендерит подзадачи как обычные строки таблицы — без плана и стадий.
        childrenColumnName: '__none__',
        // ?? — ответ, закэшированный до появления подзадач (или сервер старее
        // фронта на выкатке), приходит без поля children.
        rowExpandable: (p) => (p.children ?? []).length > 0,
        expandedRowRender: (p) => <ChildrenList items={p.children ?? []} />,
        expandRowByClick: false,
      }}
      onRow={(p) => ({
        onClick: (e) => {
          // Стрелка раскрытия живёт внутри строки — без этой проверки клик по
          // ней и разворачивал бы подзадачи, и уводил в карточку проекта.
          if ((e.target as HTMLElement).closest('.ant-table-row-expand-icon')) return;
          onRowClick(p.key);
        },
        style: { cursor: 'pointer' },
      })}
      summary={() => (
        // fixed="bottom" — строка итогов видна и при прокрутке списка.
        <Table.Summary fixed="bottom">
        <Table.Summary.Row>
          {/* Пустая ячейка под колонку со стрелкой раскрытия — иначе итоги съедут влево. */}
          <Table.Summary.Cell index={0} />
          <Table.Summary.Cell index={1}>
            <span style={{ color: DARK_THEME.textPrimary, fontWeight: 600 }}>
              Итого · {projects.length}
            </span>
          </Table.Summary.Cell>
          <Table.Summary.Cell index={2} align="right">
            <span style={{ color: DARK_THEME.textPrimary, fontWeight: 600, whiteSpace: 'nowrap' }}>
              {Math.round(totals.totalFact)} / {totals.totalPlan === null ? '—' : Math.round(totals.totalPlan)} ч
            </span>
          </Table.Summary.Cell>
          <Table.Summary.Cell index={3} align="right">
            <span style={{ color: pctColor(totals.totalPct), fontWeight: 600 }}>
              {totals.totalPct === null ? '—' : `${totals.totalPct}%`}
            </span>
          </Table.Summary.Cell>
          {STAGES.map((s, i) => (
            <Table.Summary.Cell key={s.code} index={4 + i} align="right">
              <StageCell wt={totals.workTypes.find((w) => w.code === s.code)} />
            </Table.Summary.Cell>
          ))}
          {hasExternal && (
            <Table.Summary.Cell index={4 + STAGES.length} align="right">
              <span style={{ color: DARK_THEME.textMuted }}>
                {totals.externalHours > 0 ? `${Math.round(totals.externalHours)} ч` : '—'}
              </span>
            </Table.Summary.Cell>
          )}
        </Table.Summary.Row>
        </Table.Summary>
      )}
    />
  );
};

function findWt(p: PortfolioProject, code: string): PlanWorkType | undefined {
  return p.work_types.find((w) => w.code === code);
}
