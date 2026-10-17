import { useSearchParams } from 'react-router';
import { Card, Col, Row, Select, Statistic, Table, Tag, Empty } from 'antd';
import dayjs from 'dayjs';
import PageHeader from '../components/shared/PageHeader';
import compareHelp from '../../../docs/help/scenario-compare.md?raw';
import { useResourcePlans, usePlanDiff } from '../hooks/useResourcePlanning';
import { useGlobalTeamFilter } from '../hooks/useGlobalTeamFilter';
import { useRegisterHelp } from '../contexts/HelpContext';
import type { AssignmentShift } from '../api/resourcePlanning';
import { PHASE_LABELS } from '../utils/gantt';

/** Тип изменения назначения — по-русски, как в справке раздела. */
const SHIFT_LABELS: Record<AssignmentShift['kind'], string> = {
  added: 'Добавлено',
  removed: 'Убрано',
  shifted: 'Сдвинуто',
};

export default function ScenarioComparatorPage() {
  const [params, setParams] = useSearchParams();
  const baseId = params.get('base');
  const scenId = params.get('scen');
  const { selectedTeams } = useGlobalTeamFilter();
  const { data: plans = [] } = useResourcePlans(selectedTeams[0]);
  const { data: diff } = usePlanDiff(scenId, baseId);
  useRegisterHelp('Сравнение сценариев', compareHelp);

  const planOpts = plans.map(p => ({
    label: `${p.label ?? `${p.quarter} ${p.year}`} ${p.is_baseline ? '★' : ''}`.trim(),
    value: p.id,
  }));

  const shiftColor = (k: AssignmentShift['kind']) =>
    k === 'added' ? 'green' : k === 'removed' ? 'red' : 'orange';

  return (
    <div style={{ padding: '16px 24px' }}>
      <PageHeader
        title="Сравнение сценариев"
      />
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={12}>
          <Card size="small" title="Базовый план">
            <Select
              style={{ width: '100%' }}
              value={baseId}
              options={planOpts}
              onChange={v => setParams({ base: v, scen: scenId ?? '' })}
              placeholder="Выберите базовый план"
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
              placeholder="Выберите сценарий"
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
                  title="Последняя дата окончания"
                  value={diff.scenario_metrics.last_end_date
                    ? dayjs(diff.scenario_metrics.last_end_date).format('DD.MM.YYYY')
                    : '—'}
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
                { title: 'Фаза', dataIndex: 'phase', render: (v: string) => PHASE_LABELS[v] ?? v },
                { title: 'Часть', dataIndex: 'part_number' },
                {
                  title: 'Тип',
                  dataIndex: 'kind',
                  render: (k: AssignmentShift['kind']) => <Tag color={shiftColor(k)}>{SHIFT_LABELS[k] ?? k}</Tag>,
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
