import ScenarioCreateModal from './ScenarioCreateModal';
import ApproveCelebration from './ApproveCelebration';
import ScenarioDiffPanel from './ScenarioDiffPanel';
import ScenarioCompareDrawer from './ScenarioCompareDrawer';
import ScenarioRevisionHistoryDrawer from './ScenarioRevisionHistoryDrawer';
import InvolvementDefaultsDrawer from './InvolvementDefaultsDrawer';
import HoursBreakdownDrawer from '../hours/HoursBreakdownDrawer';
import EmployeeDrawer from '../capacity/EmployeeDrawer';
import type { PlanningPageModel } from '../../hooks/usePlanningPage';

/**
 * Окна и выезжающие панели страницы «Сценарии» — общие для всех раскладок.
 * Обычная функция, а не компонент: Aurora кладёт их детьми Space на прежние
 * места (фрагмент Space разворачивает поэлементно — отступы не меняются).
 */
export function planningOverlays(vm: PlanningPageModel) {
  const {
    createOpen, setCreateOpen, setScenarioId, scenario, allocations, isDraft, diffOpen, setDiffOpen,
    compareOpen, setCompareOpen, scenarioId, historyOpen, setHistoryOpen, involvementOpen,
    setInvolvementOpen, celebrate, ungroupedDrawerId, setUngroupedDrawerId, breakdown, setBreakdown, period,
  } = vm;
  return {
    create: (
      <ScenarioCreateModal
        open={createOpen}
        onClose={(createdId) => {
          setCreateOpen(false);
          if (createdId) setScenarioId(createdId);
        }}
      />
    ),
    rest: (
      <>
        {scenario && allocations && isDraft && (
          <ScenarioDiffPanel
            open={diffOpen}
            onClose={() => setDiffOpen(false)}
            draftScenario={scenario}
            draftAllocations={allocations}
          />
        )}
        <ScenarioCompareDrawer
          open={compareOpen}
          onClose={() => setCompareOpen(false)}
          initialScenarioId={scenarioId ?? undefined}
        />
        <ScenarioRevisionHistoryDrawer
          open={historyOpen}
          onClose={() => setHistoryOpen(false)}
          scenarioId={scenarioId}
        />
        <InvolvementDefaultsDrawer
          open={involvementOpen}
          onClose={() => setInvolvementOpen(false)}
          team={scenario?.team ?? null}
          scenarioId={scenarioId}
        />
        <ApproveCelebration visible={celebrate} />
        <EmployeeDrawer
          employeeId={ungroupedDrawerId}
          onClose={() => setUngroupedDrawerId(null)}
        />
        <HoursBreakdownDrawer
          open={breakdown.open}
          onClose={() => setBreakdown((b) => ({ ...b, open: false }))}
          issueId={breakdown.issueId}
          issueKey={breakdown.issueKey}
          year={period.year}
          quarter={period.quarter}
        />
      </>
    ),
  };
}
