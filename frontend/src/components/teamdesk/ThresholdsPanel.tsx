import { useState } from 'react';
import { App, Button, Card, Checkbox, InputNumber, Select, Space, Typography } from 'antd';
import type { DeskSettings, FlagCode } from '../../api/teamDesk';
import { FLAG_ICON, FLAG_LABELS, FLAG_ORDER } from '../../api/teamDesk';
import { useSaveDeskSettings } from '../../hooks/useTeamDesk';

/**
 * Порог и признак, который он обслуживает. Признак выключен — порог не нужен:
 * настраивать нечего, и в панели он только мешает. Порог без признака
 * (`flag: null`) показывается всегда.
 */
const FIELDS: { key: string; label: string; suffix: string; flag: FlagCode | null }[] = [
  { key: 'decomposition_hours', label: 'Декомпозиция обязательна от', suffix: 'ч', flag: 'decomp' },
  { key: 'overrun_pct', label: 'Перерасход от', suffix: '%', flag: 'over' },
  { key: 'underrun_pct', label: 'Недорасход от', suffix: '%', flag: 'under' },
  { key: 'stale_days', label: 'Зависла, дней в статусе', suffix: '', flag: 'stale' },
  { key: 'child_gap_pct', label: 'Оценки подзадач ниже родителя на', suffix: '%', flag: 'childgap' },
  { key: 'wip_limit', label: 'Лимит задач в работе', suffix: '', flag: null },
  { key: 'rubber_days', label: 'Резиновая задача: дней в очередь', suffix: 'дн', flag: null },
];

interface Props {
  settings: DeskSettings;
  /** Статусы, встретившиеся в срезе, в порядке групп. */
  statusOptions: string[];
  statusCounters: string[];
  onStatusCountersChange: (v: string[]) => void;
}

/**
 * Настройки вида раздела: какие признаки отслеживаются, пороги подсветки и
 * набор счётчиков статусов. Настраивается разово, поэтому спрятано за шестерёнкой.
 */
export function ThresholdsPanel({
  settings, statusOptions, statusCounters, onStatusCountersChange,
}: Props) {
  const { message } = App.useApp();
  const [draft, setDraft] = useState<Record<string, number>>(settings.thresholds);
  const [disabled, setDisabled] = useState<FlagCode[]>(settings.disabled_flags ?? []);
  const save = useSaveDeskSettings();

  // Черновик сбрасывается через key на вызывающей стороне — переживший
  // сохранение стейт иначе показывал бы старые числа.
  const off = new Set(disabled);
  const dirty =
    FIELDS.some((f) => draft[f.key] !== settings.thresholds[f.key]) ||
    JSON.stringify([...disabled].sort()) !==
      JSON.stringify([...(settings.disabled_flags ?? [])].sort());

  const toggle = (flag: FlagCode, on: boolean) =>
    setDisabled(on ? disabled.filter((f) => f !== flag) : [...disabled, flag]);

  return (
    <Card size="small" styles={{ body: { padding: '10px 12px' } }}>
      <Space orientation="vertical" size={10} style={{ width: '100%' }}>
      <Space wrap size={[14, 6]} align="start">
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>ОТСЛЕЖИВАТЬ</Typography.Text>
        {FLAG_ORDER.map((flag) => (
          <Checkbox
            key={flag}
            checked={!off.has(flag)}
            onChange={(e) => toggle(flag, e.target.checked)}
          >
            <span style={{ fontSize: 12 }}>{FLAG_ICON[flag]} {FLAG_LABELS[flag]}</span>
          </Checkbox>
        ))}
      </Space>

      <Space wrap size={[18, 10]} align="end">
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>ПОРОГИ ПОДСВЕТКИ</Typography.Text>
        {FIELDS.filter((f) => !f.flag || !off.has(f.flag)).map((f) => (
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
              { ...settings, thresholds: draft, disabled_flags: disabled },
              { onSuccess: () => message.success('Настройки сохранены') },
            )
          }
        >
          Сохранить
        </Button>
      </Space>

      <Space wrap size={[18, 10]} align="end">
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          СЧЁТЧИКИ СТАТУСОВ
        </Typography.Text>
        <Space orientation="vertical" size={2}>
          <Typography.Text type="secondary" style={{ fontSize: 11 }}>
            Показывать в разрезе разработчиков
          </Typography.Text>
          <Select
            mode="multiple"
            allowClear
            size="small"
            // Пусто = все статусы среза: польза сразу, настраивать не обязательно.
            placeholder="все статусы"
            style={{ minWidth: 420 }}
            value={statusCounters}
            onChange={onStatusCountersChange}
            options={statusOptions.map((s) => ({ value: s, label: s }))}
            maxTagCount="responsive"
          />
        </Space>
      </Space>
      </Space>
    </Card>
  );
}
