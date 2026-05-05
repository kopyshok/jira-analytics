import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router';
import { App, Button, Empty, Segmented, Select, Spin, Tag } from 'antd';
import { CalculatorOutlined } from '@ant-design/icons';
import { useGanttProjection, useResourcePlans, useComputeResourcePlan } from '../hooks/useResourcePlanning';
import { useEmployees } from '../hooks/useCapacity';
import { useGlobalTeamFilter } from '../hooks/useGlobalTeamFilter';
import { usePersistedSearchParam } from '../hooks/usePersistedSearchParam';
import { sortAssignmentsByScenarioAssignee } from '../utils/sortAssignments';
import ClassicMode from '../components/resource-planning-v3/modes/ClassicMode';
import ResourceCentricMode from '../components/resource-planning-v3/modes/ResourceCentricMode';
import RoadmapMode from '../components/resource-planning-v3/modes/RoadmapMode';
import OptimizeButton from '../components/resource-planning-v2/OptimizeButton';
import PlanQualityBadge from '../components/resource-planning/PlanQualityBadge';

type Mode = 'classic' | 'resource' | 'roadmap';

export default function ResourcePlanningV3Page() {
  const { message } = App.useApp();
  const [searchParams, setSearchParams] = useSearchParams();
  const { selectedTeams } = useGlobalTeamFilter();
  const team = selectedTeams[0] ?? '';
  const initialMode = (searchParams.get('mode') as Mode) || 'classic';
  const [mode, setMode] = useState<Mode>(initialMode);
  const [planId, setPlanId] = usePersistedSearchParam('plan_id', 'resource_planning_v3_plan_id');

  const { data: plans = [], isLoading: plansLoading } = useResourcePlans(team || undefined);
  const { data: gantt, isLoading: ganttLoading } = useGanttProjection(planId);
  const { data: allEmployees = [] } = useEmployees({ isActive: true });
  const employees = team ? allEmployees.filter(e => e.team === team) : allEmployees;

  const handleModeChange = (m: Mode) => {
    setMode(m);
    const next = new URLSearchParams(searchParams);
    next.set('mode', m);
    setSearchParams(next);
  };

  const handlePlanChange = (id: string | null) => setPlanId(id);

  const sortedAssignments = useMemo(
    () => (gantt ? sortAssignmentsByScenarioAssignee(gantt.assignments) : []),
    [gantt],
  );

  const compute = useComputeResourcePlan();
  const handleCompute = async () => {
    if (!planId) return;
    try {
      await compute.mutateAsync(planId);
      message.success('Расписание рассчитано');
    } catch {
      message.error('Ошибка расчёта');
    }
  };

  return (
    <div style={{ padding: 0, height: 'calc(100vh - 64px)', display: 'flex', flexDirection: 'column', background: '#141414' }}>
      <div style={{ padding: '12px 24px', borderBottom: '1px solid #303030', display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap', flexShrink: 0 }}>
        <h2 style={{ margin: 0, fontSize: 16, color: '#e6e6e6' }}>Планирование <Tag color="cyan">γ</Tag></h2>
        <Select
          loading={plansLoading}
          placeholder="Выберите план"
          value={planId}
          onChange={handlePlanChange}
          options={plans.map(p => ({
            label: `${p.quarter ?? '—'} ${p.year ?? ''} — ${p.team ?? '—'} [${p.status}]${p.label ? ' · ' + p.label : ''}`,
            value: p.id,
          }))}
          style={{ minWidth: 360 }}
          allowClear
        />
        <Segmented
          value={mode}
          onChange={v => handleModeChange(v as Mode)}
          options={[
            { label: 'Классика', value: 'classic' },
            { label: 'Ресурсо-центричный', value: 'resource' },
            { label: 'Roadmap', value: 'roadmap' },
          ]}
        />
        <PlanQualityBadge planId={planId} />
        {planId && (
          <Button
            icon={<CalculatorOutlined />}
            loading={compute.isPending || gantt?.plan.status === 'computing'}
            onClick={handleCompute}
          >
            Распределить (legacy)
          </Button>
        )}
        {planId && (
          <OptimizeButton
            planId={planId}
            onSwitchPlan={id => handlePlanChange(id)}
          />
        )}
      </div>
      <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', position: 'relative' }}>
        {!planId && !ganttLoading && (
          <Empty description="Выберите план" style={{ paddingTop: 80, color: '#8c8c8c' }} />
        )}
        {ganttLoading && <Spin style={{ display: 'block', margin: '80px auto' }} />}
        {gantt && planId && !ganttLoading && (
          <>
            {mode === 'classic' && (
              <ClassicMode
                assignments={sortedAssignments}
                conflicts={gantt.conflicts}
                employees={employees}
                quarter={gantt.plan.quarter ?? 'Q3'}
                year={gantt.plan.year ?? new Date().getFullYear()}
              />
            )}
            {mode === 'resource' && (
              <ResourceCentricMode
                assignments={sortedAssignments}
                conflicts={gantt.conflicts}
                employees={employees}
                quarter={gantt.plan.quarter ?? 'Q3'}
                year={gantt.plan.year ?? new Date().getFullYear()}
              />
            )}
            {mode === 'roadmap' && (
              <RoadmapMode
                assignments={sortedAssignments}
                conflicts={gantt.conflicts}
                employees={employees}
                quarter={gantt.plan.quarter ?? 'Q3'}
                year={gantt.plan.year ?? new Date().getFullYear()}
              />
            )}
          </>
        )}
      </div>
    </div>
  );
}
