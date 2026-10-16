import { Button, Switch } from 'antd';
import { BgColorsOutlined } from '@ant-design/icons';
import type { ResourcePlanningPageState } from '../../hooks/useResourcePlanningPage';

/** Содержимое окна «Вид» ресурсного планирования — общее для всех раскладок страницы. */
export default function RpViewOptions({ state }: { state: ResourcePlanningPageState }) {
  const {
    viewMode, layout, prefs, patchPrefs, showRelayArrows, setShowRelayArrows,
    subgroupOrder, groupBySubgroup, setGroupBySubgroup, depDrawMode, setDepDrawMode,
    gantt, toggleCollapseAll, setAppearanceOpen,
  } = state;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10, minWidth: 220 }}>
      {viewMode === 'two-level' && (
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
          <Switch
            checked={prefs.hide_weekends}
            onChange={(v) => patchPrefs({ hide_weekends: v })}
            size="small"
          />
          Только рабочие дни
        </label>
      )}
      {viewMode !== 'resource-track' && layout === 'tasks' && (
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
          <Switch checked={showRelayArrows} onChange={setShowRelayArrows} size="small" />
          Стрелки эстафеты
        </label>
      )}
      {viewMode === 'two-level' && layout === 'tasks' && subgroupOrder.length > 0 && (
        <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }}>
          <Switch checked={groupBySubgroup} onChange={setGroupBySubgroup} size="small" />
          Разбить по группам
        </label>
      )}
      {viewMode === 'two-level' && layout === 'tasks' && (
        <Button
          size="small"
          type={depDrawMode ? 'primary' : 'default'}
          danger={depDrawMode}
          onClick={() => setDepDrawMode(v => !v)}
        >
          {depDrawMode ? 'Выключить рисование связей' : 'Рисовать связи'}
        </Button>
      )}
      {viewMode === 'two-level' && layout === 'tasks' && gantt && (
        <Button size="small" onClick={toggleCollapseAll}>
          {(prefs.collapsed_initiative_ids ?? []).length > 0 ? '↥ Развернуть все' : '↧ Свернуть все'}
        </Button>
      )}
      <Button size="small" icon={<BgColorsOutlined />} onClick={() => setAppearanceOpen(true)}>
        Цвета
      </Button>
    </div>
  );
}
