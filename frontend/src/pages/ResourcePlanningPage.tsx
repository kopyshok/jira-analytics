import { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router';
import { App, Button, Empty, Input, Modal, Select, Segmented, Space, Spin, Switch, Tag } from 'antd';
import {
  BarChartOutlined,
  CalculatorOutlined,
  ScheduleOutlined,
  SettingOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import PageHeader from '../components/shared/PageHeader';
import GanttChart from '../components/resource-planning/GanttChart';
import ConflictPanel from '../components/resource-planning/ConflictPanel';
import ScheduledBlocksModal from '../components/resource-planning/ScheduledBlocksModal';
import type { ViewMode } from '../components/resource-planning/GanttRows';
import {
  useGanttProjection, useResourcePlans, useComputeResourcePlan,
  useScheduledBlocks, useCreateResourcePlan, useForkPlan,
} from '../hooks/useResourcePlanning';
import { useEmployees } from '../hooks/useCapacity';
import { useGlobalTeamFilter } from '../hooks/useGlobalTeamFilter';

export default function ResourcePlanningPage() {
  const { message } = App.useApp();
  const [searchParams, setSearchParams] = useSearchParams();
  const { selectedTeams } = useGlobalTeamFilter();
  const team = selectedTeams[0] ?? '';

  const navigate = useNavigate();
  const [planId, setPlanId] = useState<string | null>(searchParams.get('plan_id'));
  const [viewMode, setViewMode] = useState<ViewMode>('two-level');
  const [blocksOpen, setBlocksOpen] = useState(false);
  const [showRelayArrows, setShowRelayArrows] = useState(true);
  const [forkModalOpen, setForkModalOpen] = useState(false);
  const [forkLabel, setForkLabel] = useState('');
  const forkMutation = useForkPlan();

  const scenarioId = searchParams.get('scenario_id');
  const { data: plans = [], isLoading: plansLoading } = useResourcePlans(team || undefined);
  const { data: gantt, isLoading: ganttLoading } = useGanttProjection(planId);
  const { data: blocks = [] } = useScheduledBlocks(team || undefined);
  const { data: allEmployees = [] } = useEmployees({ isActive: true });
  const employees = team ? allEmployees.filter(e => e.team === team) : allEmployees;
  const compute = useComputeResourcePlan();
  const createPlan = useCreateResourcePlan();

  useEffect(() => {
    if (scenarioId && !planId && !plansLoading) {
      const existing = plans.find(p => p.scenario_id === scenarioId);
      if (existing) {
        setPlanId(existing.id);
        setSearchParams({ plan_id: existing.id });
      } else if (plans.length === 0) {
        createPlan.mutateAsync({
          scenario_id: scenarioId,
          team,
          quarter: searchParams.get('quarter') ?? 'Q2',
          year: parseInt(searchParams.get('year') ?? String(new Date().getFullYear())),
        }).then(plan => {
          setPlanId(plan.id);
          setSearchParams({ plan_id: plan.id });
        }).catch(() => message.error('Ошибка создания плана'));
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scenarioId, planId, plansLoading, plans.length]);

  const handleCompute = async () => {
    if (!planId) return;
    try {
      await compute.mutateAsync(planId);
      message.success('Расписание рассчитано');
    } catch {
      message.error('Ошибка расчёта');
    }
  };

  const planOptions = plans.map(p => {
    const isCopy = !!p.parent_plan_id;
    const labelText = p.label ? ` · ${p.label}` : '';
    const copyMark = isCopy ? ' (копия)' : '';
    return {
      label: `${p.quarter} ${p.year} — ${p.team ?? '—'}${copyMark}${labelText} [${p.status}]`,
      value: p.id,
    };
  });

  return (
    <div style={{ padding: '16px 24px' }}>
      <PageHeader
        title="Ресурсное планирование"
        actions={
          <Space>
            <Button icon={<SettingOutlined />} onClick={() => setBlocksOpen(true)} size="small">
              Заблокированные периоды
            </Button>
          </Space>
        }
      />

      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 16, flexWrap: 'wrap' }}>
        <Select
          loading={plansLoading}
          placeholder="Выберите план"
          value={planId}
          onChange={id => { setPlanId(id); setSearchParams(id ? { plan_id: id } : {}); }}
          options={planOptions}
          style={{ minWidth: 320 }}
          allowClear
        />
        {planId && (
          <Button
            icon={<CalculatorOutlined />}
            type="primary"
            loading={compute.isPending || gantt?.plan.status === 'computing'}
            onClick={handleCompute}
          >
            Пересчитать
          </Button>
        )}
        {gantt && (
          <Tag color={gantt.plan.status === 'ready' ? 'cyan' : 'orange'}>
            {gantt.plan.status === 'ready' ? 'Готово' : gantt.plan.status}
          </Tag>
        )}
        {gantt?.plan.label && <Tag color="purple">{gantt.plan.label}</Tag>}
        {gantt?.plan.is_baseline && <Tag color="cyan">Базовый</Tag>}
        {planId && gantt && (
          <Button size="small" onClick={() => setForkModalOpen(true)}>
            Сделать копию
          </Button>
        )}
        {gantt?.plan.parent_plan_id && (
          <Button
            size="small"
            onClick={() => navigate(`/resource-planning/compare?base=${gantt.plan.parent_plan_id}&scen=${planId}`)}
          >
            Сравнить с базовым
          </Button>
        )}

        <Space size={4} style={{ marginLeft: 'auto' }}>
          {viewMode !== 'resource-track' && (
            <Space size={4}>
              <Switch
                checked={showRelayArrows}
                onChange={setShowRelayArrows}
                size="small"
              />
              <span style={{ fontSize: 12, color: '#8ab0d8' }}>Связи</span>
            </Space>
          )}
          <Segmented
            value={viewMode}
            onChange={v => setViewMode(v as ViewMode)}
            options={[
              { label: 'Портфель', value: 'portfolio', icon: <BarChartOutlined /> },
              { label: 'Фазы', value: 'two-level', icon: <ScheduleOutlined /> },
              { label: 'Ресурсы', value: 'resource-track', icon: <TeamOutlined /> },
            ]}
          />
        </Space>
      </div>

      {gantt && <ConflictPanel conflicts={gantt.conflicts} planId={planId} />}

      {ganttLoading && <Spin style={{ display: 'block', margin: '80px auto' }} />}
      {!planId && !ganttLoading && (
        <Empty description="Выберите план или создайте его из утверждённого сценария" />
      )}
      {gantt && !ganttLoading && planId && (
        <GanttChart
          assignments={gantt.assignments}
          blocks={blocks}
          quarter={gantt.plan.quarter ?? 'Q1'}
          year={gantt.plan.year ?? new Date().getFullYear()}
          viewMode={viewMode}
          showRelayArrows={showRelayArrows}
          planId={planId}
          employees={employees}
        />
      )}

      <ScheduledBlocksModal open={blocksOpen} onClose={() => setBlocksOpen(false)} team={team || undefined} />

      <Modal
        open={forkModalOpen}
        title="Сделать копию плана"
        okText="Создать"
        cancelText="Отмена"
        onOk={async () => {
          if (!planId) return;
          try {
            const newPlan = await forkMutation.mutateAsync({ planId, label: forkLabel || undefined });
            setForkModalOpen(false);
            setForkLabel('');
            setPlanId(newPlan.id);
            setSearchParams({ plan_id: newPlan.id });
            message.success('План скопирован');
          } catch {
            message.error('Ошибка создания копии');
          }
        }}
        onCancel={() => { setForkModalOpen(false); setForkLabel(''); }}
        confirmLoading={forkMutation.isPending}
      >
        <Input
          placeholder="Метка сценария (например: «+1 разработчик»)"
          value={forkLabel}
          onChange={e => setForkLabel(e.target.value)}
          autoFocus
        />
      </Modal>
    </div>
  );
}
