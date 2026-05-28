import { Button, Card, Space, Tag, Progress, Typography, Select } from 'antd';
import { SyncOutlined, StopOutlined, CheckCircleOutlined, CloseCircleOutlined, LoadingOutlined } from '@ant-design/icons';
import { useState } from 'react';
import { useSyncPipeline, type PipelineStageState } from '../../hooks/useSyncPipeline';
import type { PipelineMode } from '../../api/syncPipeline';
import { DARK_THEME } from '../../utils/constants';
import { trackAction } from '../../lib/usage/track';

const { Text } = Typography;

const MODE_LABELS: Record<PipelineMode, string> = {
  quick: 'Быстрый (ворклоги)',
  normal: 'Обычный (задачи + ворклоги)',
  full: 'Полный (всё заново)',
  team: 'По команде',
};

function StageRow({ stage }: { stage: PipelineStageState }) {
  const icon =
    stage.status === 'running' ? <LoadingOutlined style={{ color: DARK_THEME.cyanPrimary }} /> :
    stage.status === 'done' ? <CheckCircleOutlined style={{ color: '#52c41a' }} /> :
    stage.status === 'failed' ? <CloseCircleOutlined style={{ color: '#ff4d4f' }} /> :
    null;

  const countsText = stage.counts
    ? Object.entries(stage.counts)
        .map(([k, v]) => `${k}: ${v}`)
        .join(' · ')
    : null;

  return (
    <Space size={8}>
      {icon}
      <Text style={{ fontSize: 13 }}>{stage.stage}</Text>
      {countsText && <Text type="secondary" style={{ fontSize: 12 }}>{countsText}</Text>}
      {stage.error && <Text type="danger" style={{ fontSize: 12 }}>{stage.error}</Text>}
    </Space>
  );
}

type Props = {
  /** Список команд для режима «По команде» (опционально). */
  teams?: string[];
};

export default function PipelineRunner({ teams = [] }: Props) {
  const { state, start, cancel, reset } = useSyncPipeline();
  const [mode, setMode] = useState<PipelineMode>('normal');
  const [team, setTeam] = useState<string | undefined>(undefined);

  const isRunning = state.status === 'running';

  const handleStart = () => {
    start(mode, mode === 'team' ? team : undefined);
    trackAction('sync_started');
  };

  const handleCancel = () => {
    cancel();
    trackAction('sync_cancelled');
  };

  const statusTag =
    state.status === 'done' ? <Tag color="success">Завершён</Tag> :
    state.status === 'failed' ? <Tag color="error">Ошибка</Tag> :
    state.status === 'cancelled' ? <Tag color="warning">Прерван</Tag> :
    null;

  return (
    <Card
      title={
        <Space>
          <SyncOutlined />
          Запуск синхронизации
          {statusTag}
        </Space>
      }
      size="small"
      extra={
        state.status !== 'idle' && state.status !== 'running' ? (
          <Button size="small" onClick={reset}>Сбросить</Button>
        ) : null
      }
    >
      <Space orientation="vertical" style={{ width: '100%' }}>
        <Space wrap>
          <Select
            value={mode}
            onChange={setMode}
            disabled={isRunning}
            style={{ minWidth: 240 }}
            options={Object.entries(MODE_LABELS).map(([value, label]) => ({ value, label }))}
          />
          {mode === 'team' && (
            <Select
              placeholder="Выберите команду"
              value={team}
              onChange={setTeam}
              disabled={isRunning}
              style={{ minWidth: 200 }}
              allowClear
              options={teams.map((t) => ({ value: t, label: t }))}
            />
          )}
          {isRunning ? (
            <Button danger icon={<StopOutlined />} onClick={handleCancel}>
              Прервать
            </Button>
          ) : (
            <Button
              type="primary"
              icon={<SyncOutlined />}
              onClick={handleStart}
              disabled={mode === 'team' && !team}
            >
              Запустить
            </Button>
          )}
        </Space>

        {isRunning && (
          <Progress
            percent={99.9}
            status="active"
            showInfo={false}
            strokeColor={DARK_THEME.cyanPrimary}
          />
        )}

        {state.error && (
          <Text type="danger" style={{ fontSize: 12 }}>{state.error}</Text>
        )}

        {state.stages.length > 0 && (
          <Space orientation="vertical" size={4} style={{ width: '100%', paddingTop: 4 }}>
            {state.stages.map((s) => (
              <StageRow key={s.stage} stage={s} />
            ))}
          </Space>
        )}

        {state.runId && (
          <Text type="secondary" style={{ fontSize: 11 }}>Run: {state.runId}</Text>
        )}
      </Space>
    </Card>
  );
}
