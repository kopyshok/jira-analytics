import { useMemo, useState } from 'react';
import { App } from 'antd';

import EmployeeLoadHeatmap, { type EmployeeLoadHeatmapProps } from './EmployeeLoadHeatmap';
import WatchPickerModal from './WatchPickerModal';
import { usePlanWatch, useRemovePlanWatch } from '../../hooks/useResourcePlanning';

type Props = Omit<EmployeeLoadHeatmapProps, 'watchRows' | 'watchBookings' | 'onRemoveWatch' | 'onPickPeople'> & {
  planId: string;
};

/** «Загрузка по дням» плана со списком наблюдения: «Подобрать людей» и секция «Наблюдаемые». */
export default function PlanLoadHeatmap({ planId, ...heatmap }: Props) {
  const { message } = App.useApp();
  const { data: watch } = usePlanWatch(planId);
  const remove = useRemovePlanWatch();
  const [pickerOpen, setPickerOpen] = useState(false);
  // В выборе нет людей плана и уже наблюдаемых.
  const excludeIds = useMemo(
    () => [...heatmap.rows, ...(watch?.rows ?? [])].map((r) => r.employee_id),
    [heatmap.rows, watch],
  );
  // Дни строк — квартал плана: по нему «вся роль в команде» берёт состав.
  const days = heatmap.rows[0]?.days ?? [];

  return (
    <>
      <EmployeeLoadHeatmap
        {...heatmap}
        watchRows={watch?.rows}
        watchBookings={watch?.bookings}
        onRemoveWatch={(employeeId) =>
          remove.mutate(
            { planId, employeeId },
            { onError: () => message.error('Не удалось убрать из наблюдаемых') },
          )
        }
        onPickPeople={() => setPickerOpen(true)}
      />
      {pickerOpen && days.length > 0 && (
        <WatchPickerModal
          open
          onClose={() => setPickerOpen(false)}
          planId={planId}
          excludeIds={excludeIds}
          quarterStart={days[0].date}
          quarterEnd={days[days.length - 1].date}
        />
      )}
    </>
  );
}
