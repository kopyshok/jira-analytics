import { Alert, Table, Tag, Typography } from 'antd';
import type { HoursRow, HoursSummary, PostCheck } from '../../../api/jiraMigration';
import { fmtDateTime, formatDiff, formatHours } from '../../../utils/jiraMigration';

interface Props {
  hours?: HoursSummary;
  offsetHours: number | null;
  offsetMatches: number;
  offsetSample: number;
  offsetUnexpected?: boolean;
  postCheck: PostCheck | null;
}

function HoursTable({ rows, dbTitle, dcTitle }: { rows: HoursRow[]; dbTitle: string; dcTitle: string }) {
  return (
    <Table<HoursRow>
      rowKey={(r) => `${r.team}|${r.month}`}
      size="small"
      dataSource={rows}
      pagination={{ pageSize: 50, showSizeChanger: false }}
      scroll={{ x: 'max-content' }}
      sticky
      columns={[
        { title: 'Месяц', dataIndex: 'month', width: 110 },
        { title: 'Команда', dataIndex: 'team' },
        { title: dbTitle, dataIndex: 'db_hours', align: 'right', render: (v: number) => formatHours(v) },
        { title: dcTitle, dataIndex: 'dc_hours', align: 'right', render: (v: number) => formatHours(v) },
        {
          title: 'Разница',
          key: 'diff',
          width: 120,
          align: 'right',
          render: (_: unknown, row) =>
            row.flagged ? <Tag color="red">{formatDiff(row)}</Tag> : formatDiff(row),
        },
      ]}
    />
  );
}

export default function HoursSection({ hours, offsetHours, offsetMatches, offsetSample, offsetUnexpected, postCheck }: Props) {
  if (!hours) return null;
  const flagged = hours.rows.filter((r) => r.flagged).length;
  const matchesText = offsetSample ? ` (совпало ${offsetMatches} из ${offsetSample} проверенных списаний)` : '';
  let offsetText = '';
  if (offsetHours === 0) offsetText = ` Время списаний в базе и в новой Jira совпадает${matchesText}.`;
  else if (offsetHours !== null) {
    offsetText = ` Время списаний в базе отличается от новой Jira на ${offsetHours > 0 ? '+' : ''}${offsetHours} ч${matchesText}.`;
  }

  return (
    <>
      <Typography.Paragraph type="secondary">
        Часы по командам и месяцам: сколько списано в базе сервиса и сколько по тем же задачам
        списано в новой Jira. Расхождение больше 1 % подсвечено.
      </Typography.Paragraph>
      <Typography.Paragraph>
        Списаний в базе: {hours.db_worklogs.toLocaleString('ru-RU')}; в новой Jira по задачам
        базы: {hours.dc_worklogs.toLocaleString('ru-RU')} (всего в новой Jira —{' '}
        {hours.dc_worklogs_total.toLocaleString('ru-RU')}).{offsetText}
      </Typography.Paragraph>
      {offsetUnexpected && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 12 }}
          title={
            offsetHours === null
              ? 'Время списаний в старой Jira сдвинуто не на 3 ч, как ожидалось — сверка часов после переезда может расходиться'
              : `Время списаний в старой Jira сдвинуто на ${offsetHours} ч, а не на 3 ч, как ожидалось — сверка часов после переезда может расходиться`
          }
        />
      )}
      {flagged > 0 && (
        <Alert type="warning" showIcon title={`Расхождений больше 1 %: ${flagged}`} style={{ marginBottom: 12 }} />
      )}
      <HoursTable rows={hours.rows} dbTitle="В базе" dcTitle="В новой Jira" />
      {postCheck && (
        <>
          <Typography.Title level={5} style={{ marginTop: 24 }}>
            Сверка после переезда ({fmtDateTime(postCheck.checked_at)})
          </Typography.Title>
          <Typography.Paragraph type="secondary">
            Часы в базе сейчас против часов новой Jira на момент пробного прогона. Небольшая
            разница в текущем месяце — новые списания после прогона.
          </Typography.Paragraph>
          <HoursTable rows={postCheck.rows} dbTitle="В базе сейчас" dcTitle="В новой Jira (прогон)" />
        </>
      )}
    </>
  );
}
