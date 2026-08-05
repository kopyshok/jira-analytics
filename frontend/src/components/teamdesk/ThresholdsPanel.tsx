import { useState } from 'react';
import { App, Button, Card, InputNumber, Space, Typography } from 'antd';
import type { DeskSettings } from '../../api/teamDesk';
import { useSaveDeskSettings } from '../../hooks/useTeamDesk';

const FIELDS: { key: string; label: string; suffix: string }[] = [
  { key: 'decomposition_hours', label: 'Декомпозиция обязательна от', suffix: 'ч' },
  { key: 'overrun_pct', label: 'Перерасход от', suffix: '%' },
  { key: 'underrun_pct', label: 'Недорасход от', suffix: '%' },
  { key: 'stale_days', label: 'Зависла, дней в статусе', suffix: '' },
  { key: 'child_gap_pct', label: 'Оценки подзадач ниже родителя на', suffix: '%' },
  { key: 'wip_limit', label: 'Лимит задач в работе', suffix: '' },
];

/** Пороги подсветки. Меняются здесь же — подбираются на живых данных. */
export function ThresholdsPanel({ settings }: { settings: DeskSettings }) {
  const { message } = App.useApp();
  const [draft, setDraft] = useState<Record<string, number>>(settings.thresholds);
  const save = useSaveDeskSettings();

  // Черновик сбрасывается через key на вызывающей стороне — переживший
  // сохранение стейт иначе показывал бы старые числа.
  const dirty = FIELDS.some((f) => draft[f.key] !== settings.thresholds[f.key]);

  return (
    <Card size="small" styles={{ body: { padding: '10px 12px' } }}>
      <Space wrap size={[18, 10]} align="end">
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>ПОРОГИ ПОДСВЕТКИ</Typography.Text>
        {FIELDS.map((f) => (
          <Space key={f.key} orientation="vertical" size={2}>
            <Typography.Text type="secondary" style={{ fontSize: 11 }}>{f.label}</Typography.Text>
            <InputNumber
              size="small"
              min={0}
              value={draft[f.key]}
              suffix={f.suffix || undefined}
              onChange={(v) => setDraft({ ...draft, [f.key]: Number(v ?? 0) })}
              style={{ width: 110 }}
            />
          </Space>
        ))}
        <Button
          type="primary"
          size="small"
          disabled={!dirty}
          loading={save.isPending}
          onClick={() =>
            save.mutate(
              { ...settings, thresholds: draft },
              { onSuccess: () => message.success('Пороги сохранены') },
            )
          }
        >
          Сохранить
        </Button>
      </Space>
    </Card>
  );
}
