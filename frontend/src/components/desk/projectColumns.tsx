import { Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { statusTagColor } from '../../utils/status';
import { CHART_COLORS } from '../../utils/constants';
import { fmtShortRange } from './format';
import type { DeskProject } from '../../types/desk';

/** Цвет процента выполнения: зелёный ≤100%, красный >100%. */
function pctColor(pct: number): string {
  return pct > 100 ? CHART_COLORS.red : CHART_COLORS.green;
}

/** Колонки таблицы проектов — общие для «Мои проекты» и «Занятость команды». */
export function projectColumns(): ColumnsType<DeskProject> {
  return [
    {
      title: 'Задача',
      dataIndex: 'title',
      render: (_, r) =>
        r.jira_url && r.key ? (
          <Typography.Link href={r.jira_url} target="_blank" rel="noreferrer">
            {r.key} · {r.title ?? ''}
          </Typography.Link>
        ) : (
          <span>{r.title ?? r.key ?? '—'}</span>
        ),
    },
    {
      title: 'Статус',
      dataIndex: 'status',
      width: 130,
      render: (v: string | null) =>
        v ? <Tag color={statusTagColor(v, null)}>{v}</Tag> : <span>—</span>,
    },
    {
      title: 'Плановые даты',
      width: 130,
      render: (_, r) => fmtShortRange(r.start_date, r.end_date),
    },
    {
      title: 'Норма / факт',
      width: 110,
      align: 'right',
      render: (_, r) => `${r.fact_hours} / ${r.norm_hours} ч`,
    },
    {
      title: 'Выполнено',
      dataIndex: 'pct',
      width: 90,
      align: 'right',
      render: (pct: number) => (
        <span style={{ color: pctColor(pct), fontWeight: 600 }}>{pct}%</span>
      ),
    },
  ];
}
