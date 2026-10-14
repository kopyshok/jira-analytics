import { Alert, App, Card, Col, Radio, Row, Statistic, Table, Tag, Typography } from 'antd';
import type { IssueAction, IssuesSummary, MissingIssue } from '../../../api/jiraMigration';
import { useSetDecision } from '../../../hooks/useJiraMigration';

interface Props {
  summary?: IssuesSummary;
  readOnly: boolean;
}

export default function IssuesSection({ summary, readOnly }: Props) {
  const { notification } = App.useApp();
  const setDecision = useSetDecision();
  if (!summary) return null;

  const decide = (key: string, action: IssueAction) =>
    setDecision.mutate(
      { kind: 'issue', item_key: key, decision: { action } },
      { onError: (e) => notification.error({ title: 'Решение не сохранено', description: e.message }) },
    );

  const sample = summary.deletable_sample.slice(0, 10).join(', ');

  return (
    <>
      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={12} md={6}><Card size="small"><Statistic title="Задач в базе" value={summary.db_total} /></Card></Col>
        <Col xs={12} md={6}><Card size="small"><Statistic title="Нашлись в новой Jira" value={summary.matched} /></Card></Col>
        <Col xs={12} md={6}><Card size="small"><Statistic title="Новые в новой Jira" value={summary.new_in_dc} /></Card></Col>
        <Col xs={12} md={6}><Card size="small"><Statistic title="Нет в новой Jira" value={summary.missing_total} /></Card></Col>
      </Row>
      <Typography.Paragraph type="secondary">
        Задачи, которых нет в новой Jira и по которым в сервисе ничего не заводили вручную,
        при применении удаляются: {summary.deletable_total}
        {sample ? ` (например: ${sample})` : ''}. Новые задачи придут полной синхронизацией
        после применения.
      </Typography.Paragraph>
      {summary.project_not_found.length > 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          title="Проекты, которых нет в новой Jira — их задачи останутся без изменений"
          description={summary.project_not_found
            .map((p) => `${p.key} (задач: ${p.issues.toLocaleString('ru-RU')})`)
            .join(', ')}
        />
      )}
      <Typography.Title level={5}>Нужно решение: исчезнувшие задачи с данными сервиса</Typography.Title>
      <Table<MissingIssue>
        rowKey="key"
        size="small"
        dataSource={summary.missing_with_data}
        pagination={{ pageSize: 50, showSizeChanger: false }}
        locale={{ emptyText: 'Таких задач нет' }}
        columns={[
          { title: 'Задача', dataIndex: 'key', width: 120 },
          { title: 'Название', dataIndex: 'summary' },
          {
            title: 'Что есть в сервисе',
            dataIndex: 'reasons',
            render: (reasons: string[]) => reasons.map((r) => <Tag key={r}>{r}</Tag>),
          },
          {
            title: 'Решение',
            key: 'decision',
            width: 220,
            render: (_: unknown, row) => (
              <Radio.Group
                optionType="button"
                size="small"
                aria-label={`Решение по ${row.key}`}
                disabled={readOnly || (setDecision.isPending && setDecision.variables?.item_key === row.key)}
                value={row.decision?.action}
                onChange={(e) => decide(row.key, e.target.value as IssueAction)}
                options={[
                  { value: 'keep', label: 'Оставить' },
                  { value: 'delete', label: 'Удалить' },
                ]}
              />
            ),
          },
        ]}
      />
    </>
  );
}
