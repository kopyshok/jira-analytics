import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Alert, App, Button, Card, Col, Empty, Radio, Row, Space, Statistic, Table, Tag, Tooltip as AntTooltip,
  Typography,
} from 'antd';
import { DownloadOutlined, FileTextOutlined, ReloadOutlined } from '@ant-design/icons';
import {
  Area, Bar, CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { useThemeTokens } from '../../aurora/theme/useThemeTokens';
import { perfApi } from '../../api/perf';
import type {
  PerfBottleneck, PerfOverview, PerfPeriod, PerfSlowRequest, PerfVerdict,
} from '../../api/perf';

const { Text, Paragraph } = Typography;

const PERIODS: { label: string; value: PerfPeriod }[] = [
  { label: 'Последний час', value: '1h' },
  { label: 'Сутки', value: '24h' },
  { label: '7 дней', value: '7d' },
  { label: '30 дней', value: '30d' },
];

const VERDICT_COLOR: Record<PerfVerdict, string> = {
  other_load: 'orange',
  database: 'purple',
  our_code: 'red',
  db_pool: 'magenta',
  waiting: 'blue',
};

function fmtMs(ms: number | null | undefined): string {
  if (ms == null) return '—';
  if (ms < 1000) return `${Math.round(ms)} мс`;
  return `${(ms / 1000).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} с`;
}

function fmtPct(v: number | null | undefined): string {
  return v == null ? '—' : `${Math.round(v)}%`;
}

function fmtAxisTime(iso: string, period: PerfPeriod): string {
  const d = new Date(iso);
  if (period === '1h' || period === '24h') {
    return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
  }
  return d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

/** «Сервер загружен на 95%, наш сервис — 10% → похоже, ресурсы занял кто-то другой». */
function verdictCaption(reason: string, verdictLabel: string): string {
  return `${reason.charAt(0).toUpperCase()}${reason.slice(1)} → ${verdictLabel.toLowerCase()}`;
}

/** Подпись точки графика: по загрузке — если медленные из-за чужой нагрузки, иначе самая частая причина. */
function pointCaption(p: ChartPoint): string | null {
  if (p.slow === 0 || !p.verdict || !p.verdictLabel) return null;
  if (p.verdict === 'other_load' && p.host != null && p.proc != null) {
    return verdictCaption(`сервер загружен на ${fmtPct(p.host)}, наш сервис — ${fmtPct(p.proc)}`, p.verdictLabel);
  }
  return `Чаще всего: ${p.verdictLabel.toLowerCase()}`;
}

interface ChartPoint {
  label: string;
  requests: number;
  p95: number | null;
  slow: number;
  host: number | null;
  hostMax: number | null;
  proc: number | null;
  verdict: PerfVerdict | null;
  verdictLabel: string | null;
}

function ChartTip({ point, bg, border }: { point?: ChartPoint; bg: string; border: string }) {
  if (!point) return null;
  const caption = pointCaption(point);
  return (
    <div style={{ background: bg, border: `1px solid ${border}`, borderRadius: 8, padding: '8px 10px', fontSize: 12, maxWidth: 320 }}>
      <div style={{ fontWeight: 600, marginBottom: 4 }}>{point.label}</div>
      <div>Запросов: {point.requests}</div>
      <div>95% запросов быстрее: {fmtMs(point.p95)}</div>
      <div>Медленных: {point.slow}</div>
      <div>
        Процессор сервера: {fmtPct(point.host)}
        {point.hostMax != null && point.hostMax !== point.host ? ` (пик ${fmtPct(point.hostMax)})` : ''}
      </div>
      <div>Наш сервис: {fmtPct(point.proc)} от сервера</div>
      {caption && <div style={{ marginTop: 6, fontWeight: 600 }}>{caption}</div>}
    </div>
  );
}

function LoadChart({ data, period }: { data: PerfOverview; period: PerfPeriod }) {
  const t = useThemeTokens();
  const points: ChartPoint[] = data.series.map((p) => ({
    label: fmtAxisTime(p.t, period),
    requests: p.requests,
    p95: p.p95_ms,
    slow: p.slow,
    host: p.host_cpu,
    hostMax: p.host_cpu_max,
    proc: p.process_cpu,
    verdict: p.verdict,
    verdictLabel: p.verdict_label,
  }));
  const step = data.bucket_minutes >= 60 ? `${data.bucket_minutes / 60} ч` : `${data.bucket_minutes} мин`;

  return (
    <Card size="small" title={`Время ответа и загрузка сервера (одна точка — ${step})`} data-tour="perf-chart">
      <div style={{ width: '100%', height: 300 }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={points} margin={{ top: 8, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid stroke={t.border} strokeDasharray="3 3" />
            <XAxis dataKey="label" stroke={t.textMuted} tick={{ fontSize: 10.5 }} minTickGap={28} />
            <YAxis
              yAxisId="ms" stroke={t.textMuted} tick={{ fontSize: 10.5 }} width={58}
              tickFormatter={(v: number) => fmtMs(v)}
            />
            <YAxis
              yAxisId="pct" orientation="right" domain={[0, 100]} stroke={t.textMuted}
              tick={{ fontSize: 10.5 }} width={38} tickFormatter={(v: number) => `${v}%`}
            />
            {/* Столбики медленных — в нижней половине, чтобы не закрывать линии. */}
            <YAxis
              yAxisId="slow" hide allowDecimals={false}
              domain={[0, (dataMax: number) => Math.max(dataMax * 2, 4)]}
            />
            <Tooltip
              content={({ active, payload }) => (
                active ? (
                  <ChartTip
                    point={payload?.[0]?.payload as ChartPoint | undefined}
                    bg={t.pageBg}
                    border={t.border}
                  />
                ) : null
              )}
            />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Area
              yAxisId="pct" type="linear" dataKey="host" name="Процессор сервера, %"
              stroke={t.amber} fill={t.amber} fillOpacity={0.12} connectNulls isAnimationActive={false}
            />
            <Area
              yAxisId="pct" type="linear" dataKey="proc" name="Наш сервис, % от сервера"
              stroke={t.success} fill={t.success} fillOpacity={0.12} connectNulls isAnimationActive={false}
            />
            <Bar
              yAxisId="slow" dataKey="slow" name="Медленных запросов" fill={t.danger}
              maxBarSize={8} isAnimationActive={false}
            />
            <Line
              yAxisId="ms" type="linear" dataKey="p95" name="95% запросов быстрее"
              stroke={t.cyanPrimary} strokeWidth={2} dot={false} isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}

function RouteCell({ section, method, route }: { section: string; method: string; route: string }) {
  return (
    <Space orientation="vertical" size={0}>
      <Text strong>{section}</Text>
      <Text type="secondary" style={{ fontSize: 11, fontFamily: 'monospace' }}>{method} {route}</Text>
    </Space>
  );
}

function SlowDetails({ row }: { row: PerfSlowRequest }) {
  const cpu = row.duration_ms > 0 ? (row.cpu_ms / row.duration_ms) * 100 : null;
  return (
    <Space orientation="vertical" size={4} style={{ width: '100%' }}>
      <Text>
        Адрес: <Text code style={{ fontSize: 12 }}>{row.path}{row.query ? `?${row.query}` : ''}</Text>
        {' '}· ответ сервера {row.status_code}
      </Text>
      <Text>
        Ожидание базы данных: {fmtMs(row.db_ms)} из {fmtMs(row.duration_ms)}, обращений — {row.db_count}.
        {' '}Наш сервис за это время занимал процессор на {fmtPct(cpu)} одного ядра (все его запросы, не только этот).
      </Text>
      {row.host_cpu != null ? (
        <Text>
          Нагрузка в ту минуту: процессор сервера {fmtPct(row.host_cpu)}, наш сервис {fmtPct(row.process_cpu)}
          {' '}от сервера ({fmtPct(row.process_cpu_core)} одного ядра), память сервера {fmtPct(row.host_memory)},
          {' '}память сервиса {Math.round(row.process_memory_mb ?? 0)} МБ
          {row.db_pool_size != null ? `, подключения к базе ${row.db_pool_in_use} из ${row.db_pool_size}` : ''}
          , одновременно в работе до {row.requests_in_flight} запросов.
        </Text>
      ) : (
        <Text type="secondary">Снимка нагрузки сервера рядом с этим моментом нет.</Text>
      )}
      <Text strong>{verdictCaption(row.verdict_reason, row.verdict_label)}</Text>
      {row.top_queries.length > 0 && (
        <>
          <Text type="secondary">Самые долгие обращения к базе:</Text>
          {row.top_queries.map((q, i) => (
            <Paragraph
              key={i}
              copyable={{ text: q.sql }}
              style={{ margin: 0, whiteSpace: 'pre-wrap', fontFamily: 'monospace', fontSize: 12 }}
            >
              {fmtMs(q.ms)} — {q.sql}
            </Paragraph>
          ))}
        </>
      )}
    </Space>
  );
}

export default function PerformanceTab() {
  const { notification } = App.useApp();
  const [period, setPeriod] = useState<PerfPeriod>('24h');
  const [downloading, setDownloading] = useState<'md' | 'xlsx' | null>(null);

  const query = useQuery<PerfOverview>({
    queryKey: ['admin', 'perf', period],
    queryFn: () => perfApi.overview(period),
    // Неделя и месяц — тяжёлое чтение, а минута погоды там не делает: только по кнопке.
    refetchInterval: period === '1h' || period === '24h' ? 60_000 : false,
  });
  const data = query.data;

  const download = async (kind: 'md' | 'xlsx') => {
    setDownloading(kind);
    try {
      await (kind === 'md' ? perfApi.downloadReport(period) : perfApi.downloadXlsx(period));
    } catch {
      notification.error({ title: 'Не удалось скачать файл' });
    } finally {
      setDownloading(null);
    }
  };

  const slowSeconds = data ? (data.slow_ms / 1000).toLocaleString('ru-RU') : '2';

  const bottleneckColumns = [
    {
      title: 'Раздел',
      key: 'route',
      render: (_: unknown, r: PerfBottleneck) => <RouteCell section={r.section} method={r.method} route={r.route} />,
    },
    {
      title: 'Вызовов', dataIndex: 'calls', width: 90, align: 'right' as const,
      sorter: (a: PerfBottleneck, b: PerfBottleneck) => a.calls - b.calls,
      render: (v: number) => v.toLocaleString('ru-RU'),
    },
    {
      title: <AntTooltip title="Сколько времени все пользователи суммарно ждали этот запрос">Суммарно</AntTooltip>,
      dataIndex: 'total_ms', width: 100, align: 'right' as const, defaultSortOrder: 'descend' as const,
      sorter: (a: PerfBottleneck, b: PerfBottleneck) => a.total_ms - b.total_ms,
      render: (v: number) => fmtMs(v),
    },
    {
      title: 'В среднем', dataIndex: 'avg_ms', width: 100, align: 'right' as const,
      sorter: (a: PerfBottleneck, b: PerfBottleneck) => a.avg_ms - b.avg_ms,
      render: (v: number) => fmtMs(v),
    },
    {
      title: <AntTooltip title="95 запросов из 100 отвечают быстрее этого времени">95% быстрее</AntTooltip>,
      dataIndex: 'p95_ms', width: 110, align: 'right' as const,
      sorter: (a: PerfBottleneck, b: PerfBottleneck) => a.p95_ms - b.p95_ms,
      render: (v: number) => fmtMs(v),
    },
    {
      title: 'Дольше всего', dataIndex: 'max_ms', width: 110, align: 'right' as const,
      sorter: (a: PerfBottleneck, b: PerfBottleneck) => a.max_ms - b.max_ms,
      render: (v: number) => fmtMs(v),
    },
    {
      title: <AntTooltip title="Сколько раз в среднем запрос обращается к базе данных">Обращений к базе</AntTooltip>,
      dataIndex: 'db_avg_count', width: 110, align: 'right' as const,
      sorter: (a: PerfBottleneck, b: PerfBottleneck) => a.db_avg_count - b.db_avg_count,
      render: (v: number) => v.toLocaleString('ru-RU', { maximumFractionDigits: 1 }),
    },
    {
      title: <AntTooltip title="Какую часть времени запрос ждал базу данных">Доля базы</AntTooltip>,
      dataIndex: 'db_share', width: 90, align: 'right' as const,
      sorter: (a: PerfBottleneck, b: PerfBottleneck) => a.db_share - b.db_share,
      render: (v: number) => fmtPct(v * 100),
    },
    {
      title: 'Сбоев', dataIndex: 'errors_5xx', width: 80, align: 'right' as const,
      render: (v: number) => (v > 0 ? <Tag color="red">{v}</Tag> : <Text type="secondary">—</Text>),
    },
  ];

  const slowColumns = [
    {
      title: 'Когда', dataIndex: 'at', width: 160,
      render: (v: string) => new Date(v).toLocaleString('ru-RU'),
    },
    {
      title: 'Кто', dataIndex: 'user', width: 160,
      render: (v: string | null) => v ?? <Text type="secondary">—</Text>,
    },
    {
      title: 'Раздел', key: 'route',
      render: (_: unknown, r: PerfSlowRequest) => <RouteCell section={r.section} method={r.method} route={r.route} />,
    },
    {
      title: 'Длительность', dataIndex: 'duration_ms', width: 110, align: 'right' as const,
      sorter: (a: PerfSlowRequest, b: PerfSlowRequest) => a.duration_ms - b.duration_ms,
      render: (v: number) => <Text strong>{fmtMs(v)}</Text>,
    },
    {
      title: 'База', key: 'db', width: 130,
      render: (_: unknown, r: PerfSlowRequest) => `${fmtMs(r.db_ms)} · ${r.db_count} обр.`,
    },
    {
      title: <AntTooltip title="Загрузка процессора всего сервера / доля нашего сервиса в ту минуту">Сервер / наш</AntTooltip>,
      key: 'load', width: 110,
      render: (_: unknown, r: PerfSlowRequest) => (
        r.host_cpu == null ? <Text type="secondary">—</Text> : `${fmtPct(r.host_cpu)} / ${fmtPct(r.process_cpu)}`
      ),
    },
    {
      title: 'Вероятная причина', key: 'verdict', width: 230,
      render: (_: unknown, r: PerfSlowRequest) => (
        <Tag color={VERDICT_COLOR[r.verdict]} style={{ whiteSpace: 'normal' }}>{r.verdict_label}</Tag>
      ),
    },
  ];

  const verdictEntries = data
    ? (Object.entries(data.verdicts) as [PerfVerdict, number][]).sort((a, b) => b[1] - a[1])
    : [];

  return (
    <Space orientation="vertical" size="large" style={{ width: '100%' }}>
      <Alert
        data-tour="perf-about"
        type="info"
        showIcon
        title="Как быстро отвечает сервис"
        description={
          <Paragraph style={{ marginBottom: 0 }}>
            Сервис замеряет каждое обращение к нему: сколько оно длилось и сколько раз ходило в базу
            данных. Раз в минуту замеры и загрузка сервера записываются и хранятся 30 дней. Медленным
            считается ответ дольше {slowSeconds} с. Для каждого медленного ответа показана вероятная
            причина: сервер был занят чем-то другим, долгая работа с базой, медленный наш код,
            не хватило подключений к базе или ожидание внешнего сервиса либо очереди. Данные
            за текущую минуту появляются после её окончания. «Отчёт для разработки» собирает всё
            нужное разработчику в один файл.
          </Paragraph>
        }
      />

      <Space wrap data-tour="perf-toolbar">
        <Radio.Group
          value={period}
          onChange={(e) => setPeriod(e.target.value)}
          optionType="button"
          options={PERIODS}
        />
        <Button icon={<ReloadOutlined />} loading={query.isFetching} onClick={() => query.refetch()}>
          Обновить
        </Button>
        <Button icon={<FileTextOutlined />} loading={downloading === 'md'} onClick={() => download('md')}>
          Отчёт для разработки
        </Button>
        <Button icon={<DownloadOutlined />} loading={downloading === 'xlsx'} onClick={() => download('xlsx')}>
          Excel
        </Button>
      </Space>

      {query.isError && (
        <Alert
          type="error"
          showIcon
          title="Не удалось загрузить замеры"
          description={(query.error as Error).message}
          action={<Button size="small" onClick={() => query.refetch()}>Повторить</Button>}
        />
      )}

      <Row gutter={[16, 16]} data-tour="perf-tiles">
        <Col xs={12} lg={6}>
          <Card size="small" loading={query.isLoading}>
            <Statistic title="Запросов" value={data?.totals.requests ?? 0} />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card size="small" loading={query.isLoading}>
            <Statistic title={`Медленных (дольше ${slowSeconds} с)`} value={data?.totals.slow ?? 0} />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card size="small" loading={query.isLoading}>
            <Statistic title="95% запросов быстрее" value={fmtMs(data?.totals.p95_ms)} />
          </Card>
        </Col>
        <Col xs={12} lg={6}>
          <Card size="small" loading={query.isLoading}>
            <Statistic title="Сбоев сервера" value={data?.totals.errors_5xx ?? 0} />
          </Card>
        </Col>
      </Row>

      {data && (
        <Card size="small" title="Почему были медленные запросы" data-tour="perf-verdicts">
          <Space orientation="vertical" size={8} style={{ width: '100%' }}>
            {verdictEntries.length === 0 ? (
              <Text type="secondary">Медленных запросов за период не было.</Text>
            ) : (
              <Space wrap>
                {verdictEntries.map(([code, n]) => (
                  <Tag key={code} color={VERDICT_COLOR[code]}>
                    {data.verdict_labels[code]}: {n}
                  </Tag>
                ))}
                {data.verdicts_basis < data.totals.slow && (
                  <Text type="secondary">
                    причины — по последним {data.verdicts_basis.toLocaleString('ru-RU')} медленным
                  </Text>
                )}
              </Space>
            )}
            {data.load ? (
              <Text type="secondary">
                Процессор сервера: в среднем {fmtPct(data.load.host_cpu_avg)}, пик {fmtPct(data.load.host_cpu_max)}.
                {' '}Наш сервис: в среднем {fmtPct(data.load.process_cpu_avg)}, пик {fmtPct(data.load.process_cpu_max)} от
                {' '}сервера. Одновременно в работе до {data.load.requests_in_flight_max} запросов.
              </Text>
            ) : (
              <Text type="secondary">Снимков загрузки сервера пока нет — они записываются раз в минуту.</Text>
            )}
          </Space>
        </Card>
      )}

      {data && <LoadChart data={data} period={period} />}

      <Card size="small" title="Узкие места — что сильнее всего заставляет ждать" data-tour="perf-bottlenecks">
        <Table<PerfBottleneck>
          rowKey={(r) => `${r.method} ${r.route}`}
          size="small"
          loading={query.isLoading}
          dataSource={data?.bottlenecks ?? []}
          columns={bottleneckColumns}
          pagination={{ pageSize: 10, hideOnSinglePage: true }}
          scroll={{ x: 1000 }}
          locale={{ emptyText: <Empty description="Замеров за период нет" /> }}
        />
      </Card>

      <Card size="small" title="Медленные запросы" data-tour="perf-slow">
        <Table<PerfSlowRequest>
          rowKey="id"
          size="small"
          loading={query.isLoading}
          dataSource={data?.slow ?? []}
          columns={slowColumns}
          pagination={{ pageSize: 10, hideOnSinglePage: true }}
          scroll={{ x: 1000 }}
          locale={{ emptyText: <Empty description="Медленных запросов не было" /> }}
          expandable={{ expandedRowRender: (row) => <SlowDetails row={row} /> }}
        />
      </Card>
    </Space>
  );
}
