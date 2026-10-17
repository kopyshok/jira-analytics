import { useEffect, useState } from 'react';
import { InputNumber, Tooltip } from 'antd';
import { InfoCircleOutlined } from '@ant-design/icons';
import { useUpdateScenario } from '../../hooks/usePlanning';
import { DARK_THEME } from '../../utils/constants';

interface Props {
  scenarioId: string;
  value: number | null;
  disabled?: boolean;
  /** Скин: одна строка — короткая подпись «Внешний QA» с подсказкой и поле справа. */
  compact?: boolean;
}

const HINT = 'Если тестирование отдаётся внешнему исполнителю, задайте число часов. При пустом значении используются часы штатных QA.';

export default function ExternalQaInput({ scenarioId, value, disabled, compact = false }: Props) {
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

  if (compact) {
    return (
      <div className="plc-qa">
        <label className="plc-qa-label" htmlFor={`plc-qa-${scenarioId}`}>
          Внешний QA
          <Tooltip title={`Часы тестировщика (внешний ресурс) на квартал. ${HINT}`}>
            <InfoCircleOutlined className="plc-qa-hint" aria-label="Подробнее" />
          </Tooltip>
        </label>
        <InputNumber
          id={`plc-qa-${scenarioId}`}
          className="plc-qa-input"
          value={draft ?? undefined}
          onChange={(v) => setDraft(typeof v === 'number' ? v : null)}
          onBlur={handleBlur}
          min={0}
          step={10}
          precision={0}
          placeholder="не задано"
          disabled={disabled || update.isPending}
          suffix="ч"
        />
      </div>
    );
  }

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
        <Tooltip title={HINT}>
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
