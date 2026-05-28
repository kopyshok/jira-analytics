import { useEffect, useState } from 'react';
import { InputNumber, Form } from 'antd';
import { useUpdateScenario } from '../../hooks/usePlanning';

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
    // Only PATCH if changed
    if (draft === value) return;
    update.mutate({ id: scenarioId, data: { external_qa_hours: draft } });
  };

  return (
    <Form layout="vertical">
      <Form.Item
        label="Часы тестировщика (внешний ресурс) на квартал"
        tooltip="Если тестирование отдаётся внешнему исполнителю, задайте число часов. При пустом значении используются часы штатных QA."
        style={{ margin: 0 }}
      >
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
      </Form.Item>
    </Form>
  );
}
