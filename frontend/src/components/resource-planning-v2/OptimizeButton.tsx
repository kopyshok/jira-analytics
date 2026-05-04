import { useState } from 'react';
import { Button, Modal, App } from 'antd';
import { ThunderboltOutlined } from '@ant-design/icons';
import { useOptimizePlan } from '../../hooks/useResourcePlanningV2';
import type { OptimizeResult } from '../../api/resourcePlanningV2';

interface Props {
  planId: string;
  onSwitchPlan: (newPlanId: string) => void;
}

export default function OptimizeButton({ planId, onSwitchPlan }: Props) {
  const { message } = App.useApp();
  const [result, setResult] = useState<OptimizeResult | null>(null);
  const optimize = useOptimizePlan();

  const handleClick = async () => {
    try {
      const r = await optimize.mutateAsync(planId);
      setResult(r);
    } catch (err: unknown) {
      // api/client.ts throws new Error(detail) where detail may be stringified object
      // for 409 INFEASIBLE the detail object is already pushed to errorStore by the client
      const msg = err instanceof Error ? err.message : 'Ошибка оптимизации';
      // If detail was coerced from object it becomes '[object Object]' — show generic
      message.error(msg === '[object Object]' ? 'Невозможно оптимизировать: задачи не помещаются в период' : msg);
    }
  };

  return (
    <>
      <Button type="primary" icon={<ThunderboltOutlined />} loading={optimize.isPending} onClick={handleClick}>
        Оптимизировать
      </Button>
      <Modal
        open={!!result}
        title="Оптимизация завершена"
        okText="Открыть новый план"
        cancelText="Остаться на текущем"
        onOk={() => { if (result) onSwitchPlan(result.new_plan_id); setResult(null); }}
        onCancel={() => setResult(null)}
      >
        {result && (
          <div>
            <div>Статус солвера: <b>{result.solver_status}</b></div>
            <div>Время решения: {result.solve_time_ms} мс</div>
            <div style={{ marginTop: 16 }}>
              <div>Качество <b>до</b>: перегрузки {result.before.overload_days_pct}%, просрочки {result.before.late_count}, утилизация {result.before.mean_utilization_pct}%</div>
              <div>Качество <b>после</b>: перегрузки {result.after.overload_days_pct}%, просрочки {result.after.late_count}, утилизация {result.after.mean_utilization_pct}%</div>
            </div>
            {result.infeasible_items.length > 0 && (
              <div style={{ marginTop: 16, color: '#ff7875' }}>
                Не удалось разместить задачи: {result.infeasible_items.length}
              </div>
            )}
          </div>
        )}
      </Modal>
    </>
  );
}
