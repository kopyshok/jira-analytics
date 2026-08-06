import { useState } from 'react';
import {
  Alert, Button, Card, DatePicker, Input, Select, Space, Table, Tag, Typography,
} from 'antd';
import { useMutation } from '@tanstack/react-query';
import dayjs, { type Dayjs } from 'dayjs';
import KpiFunnel from '../../kpi/KpiFunnel';
import { useThemeTokens } from '../../../aurora/theme/useThemeTokens';
import { useTeams } from '../../../hooks/useSync';
import {
  explainIssue, previewMetric,
  type KpiExplainResult, type KpiMetricPayload, type KpiPreviewResult, type KpiPreviewRow,
} from '../../../api/kpi';

const { Text } = Typography;

/**
 * Предпросмотр метрики: считает то, что сейчас в форме, не сохраняя её.
 *
 * Отлаживать метрику иначе можно было только положив заведомо неверную
 * настройку в справочник, откуда её тут же подхватывал отчёт.
 */
export default function MetricPreview({ form }: { form: KpiMetricPayload }) {
  const t = useThemeTokens();
  const teamsQuery = useTeams();
  const now = new Date();

  const [team, setTeam] = useState<string | undefined>();
  const [period, setPeriod] = useState<Dayjs>(dayjs(new Date(now.getFullYear(), now.getMonth() - 1, 1)));
  const [accountId, setAccountId] = useState<string | undefined>();
  const [issueKey, setIssueKey] = useState('');
  const [result, setResult] = useState<KpiPreviewResult | null>(null);
  const [explained, setExplained] = useState<KpiExplainResult | null>(null);

  const request = () => ({
    metric: form,
    team: team as string,
    year: period.year(),
    month: period.month() + 1,
    account_id: accountId ?? null,
  });

  const previewMut = useMutation({
    mutationFn: () => previewMetric(request()),
    onSuccess: (data) => { setResult(data); setExplained(null); },
  });
  const explainMut = useMutation({
    mutationFn: () => explainIssue({ ...request(), issue_key: issueKey, side: 'numerator' }),
    onSuccess: setExplained,
  });

  const pct = (v: number | null) => (v == null ? '—' : `${Math.round(v)}%`);

  return (
    <Card size="small" title="Предпросмотр на реальных данных" style={{ marginTop: 16 }}>
      <Space wrap align="end" style={{ marginBottom: 14 }}>
        <div>
          <Text type="secondary" style={{ fontSize: 11 }}>Команда</Text><br />
          <Select
            style={{ minWidth: 260 }} value={team} onChange={(v) => { setTeam(v); setAccountId(undefined); }}
            placeholder="Выберите команду"
            options={(teamsQuery.data ?? []).map((x) => ({ value: x, label: x }))}
          />
        </div>
        <div>
          <Text type="secondary" style={{ fontSize: 11 }}>Месяц</Text><br />
          <DatePicker
            picker="month" value={period} allowClear={false}
            onChange={(v: Dayjs | null) => v && setPeriod(v)}
          />
        </div>
        <div>
          <Text type="secondary" style={{ fontSize: 11 }}>Сотрудник</Text><br />
          <Select
            allowClear style={{ minWidth: 230 }} value={accountId} onChange={setAccountId}
            placeholder="Вся команда"
            options={(result?.rows ?? []).map((r) => ({ value: r.account_id, label: r.employee_name }))}
            disabled={!result}
          />
        </div>
        <Button type="primary" disabled={!team} loading={previewMut.isPending} onClick={() => previewMut.mutate()}>
          Посчитать
        </Button>
      </Space>

      {previewMut.isError && (
        <Alert
          type="error" showIcon style={{ marginBottom: 12 }}
          title="Не удалось посчитать метрику"
          description={(previewMut.error as Error).message}
        />
      )}

      {!result && !previewMut.isPending && (
        <Text type="secondary" style={{ fontSize: 12.5 }}>
          Выберите команду и месяц — метрика посчитается по текущей форме, без сохранения.
          Список сотрудников появится после первого расчёта.
        </Text>
      )}

      {result && (
        <>
          <Space wrap size="large" style={{ marginBottom: 14 }}>
            <div>
              <Text type="secondary" style={{ fontSize: 10.5, textTransform: 'uppercase', fontWeight: 700 }}>
                Результат по команде
              </Text><br />
              <span className="num" style={{ fontSize: 24, fontWeight: 600 }}>{pct(result.team_value)}</span>
              <Text type="secondary" style={{ fontSize: 12, marginLeft: 8 }}>
                посчитано {result.people_with_data} из {result.people_total} человек
              </Text>
            </div>
            {result.items.numerator_count > 0 && (
              <div>
                <Text type="secondary" style={{ fontSize: 10.5, textTransform: 'uppercase', fontWeight: 700 }}>
                  Дробь выбранного сотрудника
                </Text><br />
                <span className="num" style={{ fontSize: 20, fontWeight: 600 }}>
                  {result.items.numerator_count} / {result.items.denominator_count}
                </span>
              </div>
            )}
          </Space>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 14 }}>
            <KpiFunnel steps={result.numerator_funnel} title="Воронка отбора · Что считаем" />
            {result.denominator_funnel.length > 0 && (
              <KpiFunnel steps={result.denominator_funnel} title="Воронка отбора · С чем сравниваем" />
            )}
          </div>

          <Table<KpiPreviewRow>
            style={{ marginTop: 14 }}
            dataSource={result.rows}
            rowKey="account_id"
            size="small"
            pagination={false}
            columns={[
              { title: 'Сотрудник', dataIndex: 'employee_name' },
              {
                title: 'Что считаем', width: 130, align: 'right',
                render: (_: unknown, r: KpiPreviewRow) => <span className="num">{r.numerator ?? '—'}</span>,
              },
              {
                title: 'С чем сравниваем', width: 160, align: 'right',
                render: (_: unknown, r: KpiPreviewRow) => <span className="num">{r.denominator ?? '—'}</span>,
              },
              {
                title: 'Значение', width: 120, align: 'right',
                render: (_: unknown, r: KpiPreviewRow) => (
                  r.has_data
                    ? <span className="num" style={{ fontWeight: 600 }}>{pct(r.value)}</span>
                    : <Text type="secondary" italic style={{ fontSize: 12 }}>нет данных</Text>
                ),
              },
            ]}
          />

          {result.items.numerator.length > 0 && (
            <div style={{ marginTop: 14 }}>
              <Text type="secondary" style={{ fontSize: 10.5, textTransform: 'uppercase', fontWeight: 700 }}>
                Что считаем · {result.items.numerator_count} задач
              </Text>
              <div style={{ marginTop: 6, fontSize: 12.5, lineHeight: 1.9 }}>
                {result.items.numerator.slice(0, 40).map((i) => (
                  <span key={i.key} style={{ marginRight: 12 }}>
                    {i.url
                      ? <a href={i.url} target="_blank" rel="noreferrer">{i.key}</a>
                      : i.key}
                  </span>
                ))}
                {result.items.numerator_count > 40 && (
                  <Text type="secondary">… ещё {result.items.numerator_count - 40}</Text>
                )}
              </div>
            </div>
          )}
        </>
      )}

      <div style={{ marginTop: 16, paddingTop: 14, borderTop: `1px solid ${t.border}` }}>
        <Text style={{ fontSize: 12.5, fontWeight: 700, display: 'block', marginBottom: 8 }}>
          Проверить конкретную задачу
        </Text>
        <Space wrap>
          <Input
            style={{ width: 180 }} placeholder="OS-14760" value={issueKey}
            onChange={(e) => setIssueKey(e.target.value)}
            onPressEnter={() => team && issueKey && explainMut.mutate()}
          />
          <Button
            disabled={!team || !issueKey} loading={explainMut.isPending}
            onClick={() => explainMut.mutate()}
          >
            Почему не попала?
          </Button>
        </Space>

        {explained && !explained.found && (
          <Alert type="warning" showIcon style={{ marginTop: 10 }}
            title={`Задача ${explained.issue_key} в базе сервиса не найдена`}
            description="Проверьте ключ или дождитесь синхронизации."
          />
        )}
        {explained?.found && (
          <div
            style={{
              marginTop: 10, padding: '10px 13px', borderRadius: 10,
              background: explained.passed
                ? `color-mix(in srgb, ${t.success} 10%, transparent)`
                : `color-mix(in srgb, ${t.danger} 10%, transparent)`,
            }}
          >
            <Text style={{ fontSize: 12.5, fontWeight: 700 }}>
              {explained.passed
                ? `Задача ${explained.issue_key} проходит все условия отбора.`
                : `Задача отсеяна на шаге «${explained.failed_step}».`}
            </Text>
            <div style={{ marginTop: 7, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {explained.steps.map((s) => (
                <Tag key={s.label} color={s.passed ? 'success' : 'error'}>{s.label}</Tag>
              ))}
            </div>
          </div>
        )}
      </div>
    </Card>
  );
}
