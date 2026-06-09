import { useEffect, useState } from 'react';
import { InputNumber, Tooltip } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
import { useUpdateScenario } from '../../hooks/usePlanning';
import { DARK_THEME } from '../../utils/constants';

interface Props {
  scenarioId: string;
  value: number | null;
  disabled?: boolean;
}

export default function ExternalQaInput({ scenarioId, value, disabled }: Props) {
  const update = useUpdateScenario();
  const [draft, setDraft] = useState<number | null>(value);

  // Sync local draft when server value changes (after save or refetch)
  useEffect(() => {
    setDraft(value);
  }, [value]);

  const handleBlur = () => {
    if (draft === value) return;
    update.mutate({ id: scenarioId, data: { external_qa_hours: draft } });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <div style={{
        fontSize: 13,
        fontWeight: 500,
        color: DARK_THEME.textSecondary,
        display: 'flex',
        alignItems: 'center',
        gap: 4,
      }}>
        Часы тестировщика (внешний ресурс) на квартал
        <Tooltip title="Если тестирование отдаётся внешнему исполнителю, задайте число часов. При пустом значении используются часы штатных QA.">
          <InfoCircleOutlined style={{ color: DARK_THEME.textMuted, cursor: 'help' }} />
        </Tooltip>
      </div>
      <InputNumber
        value={draft ?? undefined}
        onChange={(v) => setDraft(typeof v === 'number' ? v : null)}
        onBlur={handleBlur}
        min={0}
        step={10}
        precision={0}
        placeholder="не задано"
        disabled={disabled || update.isPending}
        style={{ width: '100%' }}
        suffix="ч"
      />
    </div>
  );
}
