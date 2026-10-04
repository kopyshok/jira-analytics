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
  const watchedIds = useMemo(() => (watch?.rows ?? []).map((r) => r.employee_id), [watch]);

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
      <WatchPickerModal
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        planId={planId}
        watchedIds={watchedIds}
      />
    </>
  );
}
