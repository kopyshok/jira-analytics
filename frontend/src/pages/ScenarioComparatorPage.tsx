import { useSearchParams } from 'react-router';
import { Card, Col, Row, Select, Statistic, Table, Tag, Empty } from 'antd';
import PageHeader from '../components/shared/PageHeader';
import { useResourcePlans, usePlanDiff } from '../hooks/useResourcePlanning';
import { useGlobalTeamFilter } from '../hooks/useGlobalTeamFilter';
import type { AssignmentShift } from '../api/resourcePlanning';

export default function ScenarioComparatorPage() {
  const [params, setParams] = useSearchParams();
  const baseId = params.get('base');
  const scenId = params.get('scen');
  const { selectedTeams } = useGlobalTeamFilter();
  const { data: plans = [] } = useResourcePlans(selectedTeams[0]);
  const { data: diff } = usePlanDiff(scenId, baseId);

  const planOpts = plans.map(p => ({
    label: `${p.label ?? `${p.quarter} ${p.year}`} ${p.is_baseline ? '★' : ''}`.trim(),
    value: p.id,
  }));

  const shiftColor = (k: AssignmentShift['kind']) =>
    k === 'added' ? 'green' : k === 'removed' ? 'red' : 'orange';

  return (
    <div style={{ padding: '16px 24px' }}>
      <PageHeader title="Сравнение сценариев" />
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={12}>
          <Card size="small" title="Базовый">
            <Select
              style={{ width: '100%' }}
              value={baseId}
              options={planOpts}
              onChange={v => setParams({ base: v, scen: scenId ?? '' })}
              placeholder="Выберите baseline"
              allowClear
            />
          </Card>
        </Col>
        <Col span={12}>
          <Card size="small" title="Сценарий">
            <Select
              style={{ width: '100%' }}
              value={scenId}
              options={planOpts}
              onChange={v => setParams({ base: baseId ?? '', scen: v })}
              placeholder="Выберите scenario"
              allowClear
            />
          </Card>
        </Col>
      </Row>

      {!diff && <Empty description="Выберите оба плана" />}
      {diff && (
        <>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={6}>
              <Card size="small">
                <Statistic
                  title="Назначений (база → сценарий)"
                  value={`${diff.baseline_metrics.assignments_count} → ${diff.scenario_metrics.assignments_count}`}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small">
                <Statistic
                  title="На критпути"
                  value={`${diff.baseline_metrics.critical_path_count} → ${diff.scenario_metrics.critical_path_count}`}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small">
                <Statistic
                  title="Открытые конфликты"
                  value={`${diff.baseline_metrics.conflicts_open} → ${diff.scenario_metrics.conflicts_open}`}
                  valueStyle={{
                    color: diff.scenario_metrics.conflicts_open < diff.baseline_metrics.conflicts_open
                      ? '#1e6a35' : '#e85d4a',
                  }}
                />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small">
                <Statistic
                  title="Последний end date"
                  value={diff.scenario_metrics.last_end_date ?? '—'}
                />
              </Card>
            </Col>
          </Row>

          <Card size="small" title="Изменения назначений">
            <Table
              dataSource={diff.assignment_shifts}
              rowKey={(r, i) => `${r.backlog_item_id}-${r.phase}-${r.part_number}-${i}`}
              size="small"
              pagination={{ pageSize: 20 }}
              columns={[
                {
                  title: 'Инициатива',
                  dataIndex: 'backlog_item_title',
                  render: (title: string | null, row: AssignmentShift) => title ?? row.backlog_item_id,
                },
                { title: 'Фаза', dataIndex: 'phase' },
                { title: 'Часть', dataIndex: 'part_number' },
                {
                  title: 'Тип',
                  dataIndex: 'kind',
                  render: (k: AssignmentShift['kind']) => <Tag color={shiftColor(k)}>{k}</Tag>,
                },
                {
                  title: 'Сдвиг (дни)',
                  dataIndex: 'start_delta_days',
                  render: (v: number | undefined) => v != null ? `${v > 0 ? '+' : ''}${v}` : '—',
                },
                {
                  title: 'Сменился исполнитель',
                  dataIndex: 'employee_changed',
                  render: (v: boolean | undefined) => v ? <Tag color="cyan">Да</Tag> : '',
                },
              ]}
            />
          </Card>
        </>
      )}
    </div>
  );
}
