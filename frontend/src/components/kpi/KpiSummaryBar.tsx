import { useMemo, useState } from 'react';
import { Alert, Drawer, Table, Tag, Typography } from 'antd';
import { ArrowDownOutlined, ArrowUpOutlined } from '@ant-design/icons';
import { useThemeTokens } from '../../aurora/theme/useThemeTokens';
import type {
  KpiReportRow, KpiReportSummary, KpiSkippedEmployee, KpiTeamSummaryRow,
} from '../../api/kpi';

const { Text } = Typography;

interface GapRow {
  key: string;
  metric: string;
  count: number;
  reason: string;
  people: string;
}

/**
 * Полоса итогов раздела — одной строкой.
 *
 * Раньше здесь было четыре крупные плитки и жёлтое предупреждение о нехватке
 * данных: вместе они занимали пол-экрана и повторяли то, что и так видно в
 * ведомости. Теперь строка компактная, а разбор нехватки данных и список
 * неоценённых людей открываются по клику — там их можно сделать сколько
 * угодно подробными, не отнимая места у таблицы.
 */
export default function KpiSummaryBar({
  summary, rows, prevRows, skipped, teamsSummary,
}: {
  summary?: KpiReportSummary;
  rows: KpiReportRow[];
  prevRows: KpiReportRow[];
  skipped: KpiSkippedEmployee[];
  teamsSummary: KpiTeamSummaryRow[];
}) {
  const t = useThemeTokens();
  const [drawer, setDrawer] = useState<'gaps' | 'skipped' | null>(null);

  const avgDelta = useMemo(() => {
    const avg = (list: KpiReportRow[]) => {
      const totals = list.map((r) => r.total).filter((v): v is number => v != null);
      return totals.length ? totals.reduce((s, v) => s + v, 0) / totals.length : null;
    };
    const now = avg(rows);
    const before = avg(prevRows);
    return now != null && before != null ? now - before : null;
  }, [rows, prevRows]);

  const cellsTotal = rows.reduce((s, r) => s + r.metrics.length, 0);
  const evaluated = rows.length;
  const headcount = evaluated + skipped.length;

  // Разбор нехватки данных: сколько людей пустует по каждой метрике и почему
  // именно. Норматив Cycle Time — отдельная причина: без него метрика пуста у
  // всей команды сразу, и чинится это одной настройкой.
  const gaps: GapRow[] = useMemo(() => {
    const normMissing = teamsSummary.some((s) => s.member_count > 0 && s.cycle_time_norm == null);
    const byCode = new Map<string, { name: string; people: string[] }>();
    for (const row of rows) {
      for (const m of row.metrics) {
        if (m.has_data) continue;
        const entry = byCode.get(m.code) ?? { name: m.name, people: [] };
        entry.people.push(row.employee_name);
        byCode.set(m.code, entry);
      }
    }
    return Array.from(byCode.entries()).map(([code, entry]) => {
      const everyone = entry.people.length === evaluated && evaluated > 0;
      let reason: string;
      if (code === 'cycle_time' && normMissing) {
        reason = 'Не задан норматив Cycle Time на квартал — «Настройки → KPI → Нормативы Cycle Time»';
      } else if (everyone) {
        reason = 'Пусто у всех оценённых — похоже, поле не заполняется в Jira или условия метрики никого не находят';
      } else {
        reason = 'У этих сотрудников за месяц нет ни одной подходящей задачи или записи';
      }
      return {
        key: code,
        metric: entry.name,
        count: entry.people.length,
        reason,
        people: entry.people.join(', '),
      };
    }).sort((a, b) => b.count - a.count);
  }, [rows, teamsSummary, evaluated]);

  const linkStyle = {
    background: 'none', border: 'none', padding: 0, font: 'inherit',
    color: t.cyanPrimary, cursor: 'pointer', textDecoration: 'underline dotted',
  } as const;

  return (
    <>
      <div
        style={{
          display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 18,
          padding: '10px 16px', marginBottom: 14, borderRadius: 12,
          background: t.darkAccent, border: `1px solid ${t.border}`, fontSize: 12.5,
        }}
      >
        <span>
          <Text type="secondary" style={{ fontSize: 10.5, textTransform: 'uppercase', fontWeight: 700 }}>
            Средний КЭ
          </Text>{' '}
          <b className="num" style={{ fontSize: 14 }}>
            {summary?.avg_total != null ? `${Math.round(summary.avg_total)}%` : '—'}
          </b>
          {avgDelta != null && Math.abs(avgDelta) >= 0.05 && (
            <span className="num" style={{ marginLeft: 5, color: avgDelta > 0 ? t.success : t.danger }}>
              {avgDelta > 0 ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
              {Math.abs(avgDelta).toFixed(1)} п.п.
            </span>
          )}
        </span>

        <span>
          <Text type="secondary" style={{ fontSize: 10.5, textTransform: 'uppercase', fontWeight: 700 }}>
            Ниже цели
          </Text>{' '}
          <b className="num" style={{ fontSize: 14, color: summary?.below_target_count ? t.danger : undefined }}>
            {summary ? summary.below_target_count : '—'}
          </b>
          <Text type="secondary"> из {evaluated}</Text>
        </span>

        <span>
          <Text type="secondary" style={{ fontSize: 10.5, textTransform: 'uppercase', fontWeight: 700 }}>
            Без данных
          </Text>{' '}
          <b className="num" style={{ fontSize: 14, color: summary?.no_data_metrics_count ? t.amber : undefined }}>
            {summary ? summary.no_data_metrics_count : '—'}
          </b>
          <Text type="secondary"> из {cellsTotal} клеток</Text>
          {gaps.length > 0 && (
            <button type="button" style={{ ...linkStyle, marginLeft: 8 }} onClick={() => setDrawer('gaps')}>
              разобрать
            </button>
          )}
        </span>

        <span>
          <Text type="secondary" style={{ fontSize: 10.5, textTransform: 'uppercase', fontWeight: 700 }}>
            Оценивается
          </Text>{' '}
          <b className="num" style={{ fontSize: 14, color: skipped.length ? t.amber : undefined }}>
            {evaluated} из {headcount}
          </b>
          {skipped.length > 0 && (
            <button type="button" style={{ ...linkStyle, marginLeft: 8 }} onClick={() => setDrawer('skipped')}>
              кто не попал
            </button>
          )}
        </span>
      </div>

      <Drawer
        title={drawer === 'skipped' ? 'Кто не попал в ведомость' : 'Почему не хватает данных'}
        open={drawer != null}
        onClose={() => setDrawer(null)}
        size={720}
      >
        {drawer === 'gaps' && (
          <>
            <Text type="secondary" style={{ fontSize: 12.5, display: 'block', marginBottom: 12 }}>
              Пустая клетка не обнуляет итог — её вес распределяется между остальными метриками.
              Но чем больше пустых клеток, тем менее устойчив итог: он посчитан по меньшему числу
              метрик, чем задумано профилем.
            </Text>
            <Table<GapRow>
              dataSource={gaps}
              rowKey="key"
              size="small"
              pagination={false}
              columns={[
                { title: 'Метрика', dataIndex: 'metric', width: 190 },
                {
                  title: 'Пусто у', dataIndex: 'count', width: 90, align: 'right',
                  render: (v: number) => <span className="num">{v} чел.</span>,
                },
                { title: 'Почему', dataIndex: 'reason' },
              ]}
              expandable={{
                expandedRowRender: (r) => (
                  <Text type="secondary" style={{ fontSize: 12 }}>{r.people}</Text>
                ),
                rowExpandable: (r) => r.people.length > 0,
              }}
            />
          </>
        )}

        {drawer === 'skipped' && (
          <>
            <Alert
              type="info"
              showIcon
              style={{ marginBottom: 12 }}
              title="Раздел оценивает только роли, привязанные к профилям оценки"
              description="Чтобы человек появился в ведомости, привяжите его роль к профилю в «Настройки → KPI → Профили оценки» либо заполните роль в карточке сотрудника."
            />
            <Table<KpiSkippedEmployee>
              dataSource={skipped}
              rowKey="employee_id"
              size="small"
              pagination={false}
              columns={[
                { title: 'Сотрудник', dataIndex: 'employee_name' },
                {
                  title: 'Роль', dataIndex: 'role_label', width: 220,
                  render: (label: string, r: KpiSkippedEmployee) => (
                    r.role_code
                      ? <Tag>{label}</Tag>
                      : <Tag color="warning">Роль не заполнена</Tag>
                  ),
                },
              ]}
            />
          </>
        )}
      </Drawer>
    </>
  );
}
