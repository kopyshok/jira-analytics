import { useState } from 'react';
import { useSearchParams } from 'react-router';
import { Empty, Segmented, Select, Spin, Tag } from 'antd';
import { ScheduleOutlined, TeamOutlined } from '@ant-design/icons';
import PageHeader from '../components/shared/PageHeader';
import SvarGanttChart from '../components/resource-planning-v2/SvarGanttChart';
import PlanQualityBadge from '../components/resource-planning/PlanQualityBadge';
import OptimizeButton from '../components/resource-planning-v2/OptimizeButton';
import { useGanttProjection, useResourcePlans } from '../hooks/useResourcePlanning';
import { useGlobalTeamFilter } from '../hooks/useGlobalTeamFilter';

export default function ResourcePlanningV2Page() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { selectedTeams } = useGlobalTeamFilter();
  const team = selectedTeams[0] ?? '';
  const [planId, setPlanId] = useState<string | null>(searchParams.get('plan_id'));
  const [viewMode, setViewMode] = useState<'task' | 'employee'>('task');

  const { data: plans = [], isLoading: plansLoading } = useResourcePlans(team || undefined);
  const { data: gantt, isLoading: ganttLoading } = useGanttProjection(planId);

  return (
    <div style={{ padding: '16px 24px' }}>
      <PageHeader
        title="Планирование"
        actions={<Tag color="purple">β</Tag>}
      />
      <div
        style={{
          display: 'flex',
          gap: 12,
          alignItems: 'center',
          marginBottom: 16,
          flexWrap: 'wrap',
        }}
      >
        <Select
          loading={plansLoading}
          placeholder="Выберите план"
          value={planId}
          onChange={(id: string | null) => {
            setPlanId(id);
            setSearchParams(id ? { plan_id: id } : {});
          }}
          options={plans.map(p => ({
            label: `${p.quarter} ${p.year} — ${p.team ?? '—'} [${p.status}]`,
            value: p.id,
          }))}
          style={{ minWidth: 320 }}
          allowClear
        />
        <PlanQualityBadge planId={planId} />
        {planId && (
          <OptimizeButton
            planId={planId}
            onSwitchPlan={id => { setPlanId(id); setSearchParams({ plan_id: id }); }}
          />
        )}
        <Segmented
          value={viewMode}
          onChange={(v: string | number) => setViewMode(v as 'task' | 'employee')}
          options={[
            { label: 'По задачам', value: 'task', icon: <ScheduleOutlined /> },
            { label: 'По сотрудникам', value: 'employee', icon: <TeamOutlined /> },
          ]}
        />
      </div>
      {ganttLoading && <Spin style={{ display: 'block', margin: '80px auto' }} />}
      {!planId && !ganttLoading && <Empty description="Выберите план" />}
      {gantt && !ganttLoading && planId && (
        <SvarGanttChart assignments={gantt.assignments} viewMode={viewMode} />
      )}
    </div>
  );
}
