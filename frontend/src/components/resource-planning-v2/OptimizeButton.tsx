import { useRef, useState } from 'react';
import { Button, Modal, App, Space, Tooltip } from 'antd';
import { ThunderboltOutlined, StopOutlined } from '@ant-design/icons';
import { optimizeStream, type OptimizeResult } from '../../api/resourcePlanningV2';
import { useQueryClient } from '@tanstack/react-query';

interface Props {
  planId: string;
  onSwitchPlan: (newPlanId: string) => void;
}

const SOFT_LIMIT_MS = 15_000;

export default function OptimizeButton({ planId, onSwitchPlan }: Props) {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [running, setRunning] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [result, setResult] = useState<OptimizeResult | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const handleClick = async () => {
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setRunning(true);
    setElapsedMs(0);
    try {
      const r = await optimizeStream(planId, e => setElapsedMs(e.elapsed_ms), ctrl.signal);
      setResult(r);
      queryClient.invalidateQueries({ queryKey: ['resource-plans'] });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Ошибка оптимизации';
      if ((err as Error)?.name === 'AbortError') {
        message.info('Оптимизация отменена');
      } else {
        message.error(
          msg.includes('feasible')
            ? 'Невозможно оптимизировать: задачи не помещаются в период'
            : msg,
        );
      }
    } finally {
      setRunning(false);
      abortRef.current = null;
    }
  };

  const handleCancel = () => abortRef.current?.abort();

  const elapsedSec = (elapsedMs / 1000).toFixed(0);
  const isOverdue = elapsedMs > SOFT_LIMIT_MS;

  return (
    <>
      {running ? (
        <Space>
          <Tooltip title={`Solver работает (мягкий лимит 15 сек). Можно отменить.`}>
            <Button type="primary" icon={<ThunderboltOutlined />} loading>
              {isOverdue ? `${elapsedSec} сек… (заканчивает)` : `Оптимизирую… ${elapsedSec} сек`}
            </Button>
          </Tooltip>
          <Button danger icon={<StopOutlined />} size="small" onClick={handleCancel}>
            Отменить
          </Button>
        </Space>
      ) : (
        <Tooltip title="Запустить PyJobShop-солвер. До 15 сек на план.">
          <Button type="primary" icon={<ThunderboltOutlined />} onClick={handleClick}>
            Оптимизировать
          </Button>
        </Tooltip>
      )}
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
