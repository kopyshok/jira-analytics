import { Slider, Tooltip, Typography } from 'antd';
import { DARK_THEME } from '../../utils/constants';
import { useEmbeddingThreshold, useSetEmbeddingThreshold } from '../../hooks/useThemeDictionary';

export default function EmbeddingThresholdSlider() {
  const { data } = useEmbeddingThreshold();
  const setT = useSetEmbeddingThreshold();
  const current = data?.threshold ?? 0.78;

  return (
    <Tooltip title="Выше — строже матчинг: меньше задач сматчится в существующие темы, больше пойдёт через LLM. Дефолт 0.78.">
      <div style={{ marginBottom: 12 }}>
        <Typography.Text
          style={{ fontSize: 12, color: DARK_THEME.textSecondary, display: 'block', marginBottom: 4 }}
        >
          Порог embedding-матчинга: <strong>{current.toFixed(2)}</strong>
        </Typography.Text>
        <Slider
          min={0.5}
          max={0.95}
          step={0.01}
          value={current}
          onChange={(v) => setT.mutate(v)}
          tooltip={{ formatter: (v) => (v ?? 0).toFixed(2) }}
        />
      </div>
    </Tooltip>
  );
}
