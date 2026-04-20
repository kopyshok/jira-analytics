import { useDeferredValue, useMemo, useState } from 'react';
import { App, Space } from 'antd';
import QuarterYearSelect from '../components/shared/QuarterYearSelect';
import PageHeader from '../components/shared/PageHeader';
import PlanningBacklogList from '../components/planning/PlanningBacklogList';
import PlanningCapacityPanel from '../components/planning/PlanningCapacityPanel';
import { useBacklogItems } from '../hooks/useBacklog';
import { useCapacityPreview, useGenerateScenario } from '../hooks/usePlanning';
import { useQuarterYear } from '../hooks/useQuarterYear';
import { downloadScenarioXlsx } from '../api/exports';

const EMPTY_ROLE_TOTALS = { analyst: 0, dev: 0, qa: 0 };

export default function PlanningPage() {
  const { notification } = App.useApp();
  const { year, quarter } = useQuarterYear();
  const quarterInt = Number(quarter);

  const { data: backlog } = useBacklogItems(year, `Q${quarter}`);

  // Selected backlog items (initially all, refreshes when a new backlog
  // snapshot arrives). We store the backlog identity we last reacted to as a
  // piece of React state and reconcile during render via setState-in-render
  // (React's recommended pattern for derived state) — this sidesteps both
  // `react-hooks/set-state-in-effect` and `react-hooks/refs` lint rules.
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [lastBacklog, setLastBacklog] = useState<typeof backlog | null>(null);
  if (backlog && backlog !== lastBacklog) {
    setLastBacklog(backlog);
    setSelected(new Set(backlog.map((b) => b.id)));
  }

  // Defer backlog_item_ids so that quick toggles don't spam backend; React
  // defers between renders in batches (functionally a micro-debounce).
  const selectedIds = useMemo(() => Array.from(selected).sort(), [selected]);
  const deferredIds = useDeferredValue(selectedIds);

  const previewReq = useMemo(
    () => ({
      year: Number(year),
      quarter: quarterInt,
      backlog_item_ids: deferredIds,
    }),
    [year, quarterInt, deferredIds],
  );
  const { data: preview } = useCapacityPreview(previewReq);

  const generate = useGenerateScenario();
  const [lastScenarioId, setLastScenarioId] = useState<string | null>(null);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleSave = () => {
    generate.mutate(
      {
        name: `Q${quarterInt} ${year} draft`,
        year: Number(year),
        quarter: quarterInt,
        backlog_item_ids: Array.from(selected),
      },
      {
        onSuccess: (res) => {
          setLastScenarioId(res.scenario_id);
          notification.success({
            title: `Сценарий «${res.scenario_name}» сохранён`,
            description: `Включено: ${res.included_count}, пропущено: ${res.skipped_count}`,
          });
        },
        onError: (e) =>
          notification.error({ title: 'Ошибка', description: (e as Error).message }),
      },
    );
  };

  const handleExport = () => {
    if (!lastScenarioId) return;
    downloadScenarioXlsx(lastScenarioId);
  };

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <PageHeader
        eyebrow="Планирование"
        title="Сценарии"
        subtitle="Отметьте идеи из бэклога — ёмкость по ролям пересчитывается live"
        actions={<QuarterYearSelect />}
      />

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'minmax(0, 1fr) 460px',
          gap: 16,
          alignItems: 'start',
        }}
      >
        <PlanningBacklogList
          items={backlog ?? []}
          selected={selected}
          onToggle={toggle}
          demandByRole={preview?.demand_by_role ?? EMPTY_ROLE_TOTALS}
          capacityByRole={preview?.capacity_by_role ?? EMPTY_ROLE_TOTALS}
          year={year}
          quarter={quarter}
        />
        <PlanningCapacityPanel
          preview={preview}
          quarter={quarter}
          onSave={handleSave}
          onExport={handleExport}
          isSaving={generate.isPending}
          canExport={!!lastScenarioId}
        />
      </div>
    </Space>
  );
}
