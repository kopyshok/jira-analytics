import { useEffect, useState } from 'react';
import { useSearchParams, useNavigate } from 'react-router';
import { App, Button, Empty, Input, Modal, Select, Segmented, Space, Spin, Tag } from 'antd';
import PageHeader from '../components/shared/PageHeader';
import PlanQualityBadge from '../components/resource-planning/PlanQualityBadge';
import { DhtmlxGanttChart } from '../components/resource-planning-v3';
import OptimizeButton from '../components/resource-planning-v2/OptimizeButton';
import {
  useGanttProjection, useResourcePlans, useCreateResourcePlan, useForkPlan,
} from '../hooks/useResourcePlanning';
import { useGlobalTeamFilter } from '../hooks/useGlobalTeamFilter';

type ViewMode = 'day' | 'week' | 'month';

export default function ResourcePlanningV3Page() {
  const { message } = App.useApp();
  const [searchParams, setSearchParams] = useSearchParams();
  const { selectedTeams } = useGlobalTeamFilter();
  const team = selectedTeams[0] ?? '';
  const navigate = useNavigate();

  const [planId, setPlanId] = useState<string | null>(searchParams.get('plan_id'));
  const [viewMode, setViewMode] = useState<ViewMode>('week');
  const [forkModalOpen, setForkModalOpen] = useState(false);
  const [forkLabel, setForkLabel] = useState('');
  const forkMutation = useForkPlan();

  const scenarioId = searchParams.get('scenario_id');
  const { data: plans = [], isLoading: plansLoading } = useResourcePlans(team || undefined);
  const { data: gantt, isLoading: ganttLoading } = useGanttProjection(planId);
  const createPlan = useCreateResourcePlan();

  useEffect(() => {
    if (scenarioId && !planId && !plansLoading && !createPlan.isPending) {
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
  }, [scenarioId, planId, plansLoading, plans.length, createPlan.isPending]);

  const planOptions = plans.map(p => {
    const isCopy = !!p.parent_plan_id;
    const labelText = p.label ? ` · ${p.label}` : '';
    const copyMark = isCopy ? ' (копия)' : '';
    return {
      label: `${p.quarter} ${p.year} — ${p.team ?? '—'}${copyMark}${labelText} [${p.status}]`,
      value: p.id,
    };
  });

  const isAutoFork = gantt?.plan.label === 'auto-PyJobShop';

  return (
    <div style={{ padding: '16px 24px' }}>
      <PageHeader
        title="Планирование"
        actions={
          <Space>
            <Tag color="cyan">γ</Tag>
          </Space>
        }
      />

      {/* Solver Insights panel */}
      <div
        style={{
          background: '#0f2340',
          border: '1px solid #1d2f4f',
          borderRadius: 8,
          padding: 12,
          marginBottom: 16,
        }}
      >
        <div style={{ fontSize: 12, color: '#8ab0d8', marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 }}>
          Solver Insights · DHTMLX
        </div>
        <Space wrap>
          <PlanQualityBadge planId={planId} />
          {planId && (
            <OptimizeButton
              planId={planId}
              onSwitchPlan={id => { setPlanId(id); setSearchParams({ plan_id: id }); }}
            />
          )}
          {isAutoFork && gantt?.plan.parent_plan_id && (
            <>
              <Tag color="cyan">auto-PyJobShop</Tag>
              <Button
                size="small"
                onClick={() => navigate(`/resource-planning/compare?base=${gantt.plan.parent_plan_id}&scen=${planId}`)}
              >
                Сравнить с базовым
              </Button>
            </>
          )}
        </Space>
      </div>

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
        {gantt && (() => {
          const s = gantt.plan.status;
          const label = s === 'ready' ? 'Готово'
            : s === 'stale' ? 'Требуется пересчёт'
            : s === 'computing' ? 'Считается…'
            : 'Черновик';
          const color = s === 'ready' ? 'cyan'
            : s === 'stale' ? 'orange'
            : s === 'computing' ? 'blue'
            : 'default';
          return <Tag color={color}>{label}</Tag>;
        })()}
        {gantt?.plan.label && <Tag color="purple">{gantt.plan.label}</Tag>}
        {gantt?.plan.is_baseline && <Tag color="cyan">Базовый</Tag>}
        {planId && gantt && (
          <Button size="small" onClick={() => setForkModalOpen(true)}>
            Сделать копию
          </Button>
        )}
        {gantt?.plan.parent_plan_id && !isAutoFork && (
          <Button
            size="small"
            onClick={() => navigate(`/resource-planning/compare?base=${gantt.plan.parent_plan_id}&scen=${planId}`)}
          >
            Сравнить с базовым
          </Button>
        )}

        <Segmented
          value={viewMode}
          onChange={v => setViewMode(v as ViewMode)}
          options={[
            { label: 'День', value: 'day' },
            { label: 'Неделя', value: 'week' },
            { label: 'Месяц', value: 'month' },
          ]}
          style={{ marginLeft: 'auto' }}
        />
      </div>

      {ganttLoading && <Spin style={{ display: 'block', margin: '80px auto' }} />}
      {!planId && !ganttLoading && (
        <Empty description="Выберите план или создайте его из утверждённого сценария" />
      )}
      {gantt && !ganttLoading && planId && (
        <DhtmlxGanttChart
          assignments={gantt.assignments}
          // TODO: extend useGanttProjection if backend exposes inter-initiative dependencies
          dependencies={[]}
          viewMode={viewMode}
          quarter={gantt.plan.quarter ?? 'Q1'}
          year={gantt.plan.year ?? new Date().getFullYear()}
        />
      )}

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
