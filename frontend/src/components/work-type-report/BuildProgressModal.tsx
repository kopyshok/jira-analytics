import { useEffect } from 'react';
import { Modal, Progress, Typography, Button, Space } from 'antd';
import { LoadingOutlined, CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons';
import { DARK_THEME } from '../../utils/constants';
import type { BuildStreamState } from '../../hooks/useWorkTypeReport';

const PHASE_LABELS: Record<string, string> = {
  scope: 'Подбор задач',
  map: 'Классификация задач',
  cluster: 'Группировка тем',
  reduce: 'AI-сводка',
  save: 'Сохранение',
};

interface Props {
  open: boolean;
  state: BuildStreamState;
  /** Show "done" state (controlled by parent after build finishes). */
  showDone: boolean;
  onCancel: () => void;
  onClose: () => void;
}

export default function BuildProgressModal({ open, state, showDone, onCancel, onClose }: Props) {
  const { phase, current, total, item_key, isRunning, error } = state;

  // Auto-close 1s after parent signals done
  useEffect(() => {
    if (showDone && open) {
      const t = setTimeout(onClose, 1000);
      return () => clearTimeout(t);
    }
  }, [showDone, open, onClose]);

  const isError = !!error;
  const closable = isError || showDone;

  const phasePct =
    phase === 'map' && total > 0 ? Math.round((current / total) * 100) : null;

  const phaseLabel = phase ? (PHASE_LABELS[phase] ?? phase) : '';

  return (
    <Modal
      open={open}
      title="Построение отчёта"
      closable={closable}
      onCancel={onClose}
      maskClosable={false}
      destroyOnHidden
      footer={null}
      styles={{
        body: { padding: '20px 24px 8px' },
      }}
    >
      {showDone && (
        <Space orientation="vertical" align="center" style={{ width: '100%', padding: '16px 0' }}>
          <CheckCircleOutlined style={{ fontSize: 40, color: DARK_THEME.cyanPrimary }} />
          <Typography.Text style={{ fontSize: 16, color: DARK_THEME.textPrimary }}>
            Готово
          </Typography.Text>
        </Space>
      )}

      {isError && (
        <Space orientation="vertical" align="center" style={{ width: '100%', padding: '8px 0 16px' }}>
          <CloseCircleOutlined style={{ fontSize: 32, color: '#ff4d4f' }} />
          <Typography.Text type="danger">{error}</Typography.Text>
          <Button onClick={onClose}>Закрыть</Button>
        </Space>
      )}

      {isRunning && !showDone && (
        <Space orientation="vertical" style={{ width: '100%', gap: 12 }}>
          <Space align="center">
            <LoadingOutlined style={{ color: DARK_THEME.cyanPrimary }} />
            <Typography.Text style={{ color: DARK_THEME.textPrimary, fontSize: 15 }}>
              {phaseLabel || 'Подготовка…'}
            </Typography.Text>
          </Space>

          {phasePct !== null && (
            <Progress
              percent={phasePct}
              strokeColor={DARK_THEME.cyanPrimary}
              trailColor={DARK_THEME.border}
              showInfo
            />
          )}

          {item_key && (
            <Typography.Text style={{ color: DARK_THEME.textMuted, fontSize: 12 }}>
              Текущая задача: {item_key}
            </Typography.Text>
          )}

          <div style={{ textAlign: 'right', marginTop: 8 }}>
            <Button size="small" onClick={onCancel}>
              Отмена
            </Button>
          </div>
        </Space>
      )}
    </Modal>
  );
}
