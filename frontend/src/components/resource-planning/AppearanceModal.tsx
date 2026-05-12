import { useState } from 'react';
import { App, Button, ColorPicker, Modal, Segmented, Slider, Space, Typography } from 'antd';
import type { Color } from 'antd/es/color-picker';
import type { AppearanceSettings } from '../../api/appearance';
import { DEFAULT_APPEARANCE } from '../../contexts/appearanceDefaults';
import { useUpdateAppearance } from '../../api/appearance';

const { Text } = Typography;

interface Props {
  open: boolean;
  current: AppearanceSettings;
  onClose: () => void;
}

function hexToRgb(hex: string): [number, number, number] {
  const clean = hex.replace('#', '');
  if (clean.length === 3) {
    return [
      parseInt(clean[0] + clean[0], 16),
      parseInt(clean[1] + clean[1], 16),
      parseInt(clean[2] + clean[2], 16),
    ];
  }
  return [
    parseInt(clean.slice(0, 2), 16),
    parseInt(clean.slice(2, 4), 16),
    parseInt(clean.slice(4, 6), 16),
  ];
}

function colorToHex(c: Color | string): string {
  if (typeof c === 'string') return c;
  return c.toHexString();
}

function InitiativeBarPreview({
  bracketColor,
  fillIntensity,
  animSpeed,
}: {
  bracketColor: string;
  fillIntensity: 'soft' | 'medium' | 'dense';
  animSpeed: number;
}) {
  const [r, g, b] = hexToRgb(bracketColor);
  const gradients: Record<string, string> = {
    soft: `linear-gradient(180deg, rgba(${r},${g},${b},0.10), rgba(${r},${g},${b},0.05))`,
    medium: `linear-gradient(180deg, rgba(${r},${g},${b},0.22), rgba(${r},${g},${b},0.12))`,
    dense: `linear-gradient(180deg, rgba(${r},${g},${b},0.35), rgba(${r},${g},${b},0.20))`,
  };
  const BAR_H = 22;
  return (
    <div style={{
      position: 'relative',
      width: '100%',
      height: BAR_H,
      background: gradients[fillIntensity],
    }}>
      <svg
        width="100%"
        height={BAR_H}
        preserveAspectRatio="none"
        style={{ position: 'absolute', top: 0, left: 0, overflow: 'visible' }}
      >
        <line x1="0" y1="1" x2="100%" y2="1"
          stroke={bracketColor} strokeWidth="1.5" strokeDasharray="6 4"
          className="rp-init-ants"
          style={{ animationDuration: `${animSpeed}s` }}
        />
        <line x1="0" y1={BAR_H - 1} x2="100%" y2={BAR_H - 1}
          stroke={bracketColor} strokeWidth="1.5" strokeDasharray="6 4"
          className="rp-init-ants-rev"
          style={{ animationDuration: `${animSpeed}s` }}
        />
      </svg>
      <div style={{
        position: 'absolute', left: 0, top: 0, width: 8, height: BAR_H,
        borderLeft: `2px solid ${bracketColor}`,
        borderTop: `2px solid ${bracketColor}`,
        borderBottom: `2px solid ${bracketColor}`,
      }} />
      <div style={{
        position: 'absolute', right: 0, top: 0, width: 8, height: BAR_H,
        borderRight: `2px solid ${bracketColor}`,
        borderTop: `2px solid ${bracketColor}`,
        borderBottom: `2px solid ${bracketColor}`,
      }} />
    </div>
  );
}

const PHASE_LABELS: Array<{ key: keyof AppearanceSettings['phase_colors']; label: string }> = [
  { key: 'analyst', label: 'Анализ' },
  { key: 'dev', label: 'Разработка' },
  { key: 'qa', label: 'Тестирование' },
  { key: 'opo', label: 'ОПЭ' },
];

const INTENSITY_OPTIONS = [
  { label: 'Слабая', value: 'soft' },
  { label: 'Средняя', value: 'medium' },
  { label: 'Плотная', value: 'dense' },
];

function AppearanceModalContent({ initial, onClose }: { initial: AppearanceSettings; onClose: () => void }) {
  const { notification } = App.useApp();
  const updateMutation = useUpdateAppearance();
  const [draft, setDraft] = useState<AppearanceSettings>(initial);

  const handleSave = () => {
    updateMutation.mutate(draft, {
      onSuccess: () => {
        notification.success({
          title: 'Настройки сохранены',
          description: 'Цвета планировщика обновлены.',
        });
        onClose();
      },
      onError: () => {
        notification.error({ title: 'Ошибка', description: 'Не удалось сохранить настройки.' });
      },
    });
  };

  const handleReset = () => setDraft(DEFAULT_APPEARANCE);

  const setPhaseColor = (key: keyof AppearanceSettings['phase_colors'], color: Color | string) => {
    setDraft(d => ({
      ...d,
      phase_colors: { ...d.phase_colors, [key]: colorToHex(color) },
    }));
  };

  const row = (rowKey: string, label: string, picker: React.ReactNode) => (
    <div key={rowKey} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
      <Text style={{ color: '#8ab0d8', minWidth: 130 }}>{label}</Text>
      {picker}
    </div>
  );

  return (
    <div style={{ marginTop: 8 }}>
      {PHASE_LABELS.map(({ key, label }) =>
        row(
          key,
          label,
          <ColorPicker
            value={draft.phase_colors[key]}
            onChange={(c) => setPhaseColor(key, c)}
            showText
            size="small"
          />,
        ),
      )}
      {row(
        'init-bracket',
        'Полоса инициативы',
        <ColorPicker
          value={draft.initiative_bracket_color}
          onChange={(c) => setDraft(d => ({ ...d, initiative_bracket_color: colorToHex(c) }))}
          showText
          size="small"
        />,
      )}

      <div style={{ marginBottom: 12 }}>
        <Text style={{ color: '#8ab0d8', display: 'block', marginBottom: 6 }}>Насыщенность заливки</Text>
        <Segmented
          value={draft.initiative_fill_intensity}
          onChange={(v) => setDraft(d => ({ ...d, initiative_fill_intensity: v as AppearanceSettings['initiative_fill_intensity'] }))}
          options={INTENSITY_OPTIONS}
          size="small"
          block
        />
      </div>

      <div style={{ marginBottom: 16 }}>
        <Text style={{ color: '#8ab0d8', display: 'block', marginBottom: 4 }}>
          Скорость бегущей рамки: {draft.animation_speed_seconds.toFixed(1)} с
        </Text>
        <Slider
          min={0.5}
          max={20}
          step={0.5}
          value={draft.animation_speed_seconds}
          onChange={(v) => setDraft(d => ({ ...d, animation_speed_seconds: v }))}
        />
      </div>

      <div style={{ marginBottom: 16 }}>
        <Text style={{ color: '#8ab0d8', display: 'block', marginBottom: 6 }}>Предпросмотр</Text>
        <InitiativeBarPreview
          bracketColor={draft.initiative_bracket_color}
          fillIntensity={draft.initiative_fill_intensity}
          animSpeed={draft.animation_speed_seconds}
        />
      </div>

      <Space style={{ width: '100%', justifyContent: 'flex-end' }}>
        <Button onClick={handleReset} size="small">Сбросить к умолчанию</Button>
        <Button onClick={onClose} size="small">Отмена</Button>
        <Button
          type="primary"
          onClick={handleSave}
          loading={updateMutation.isPending}
          size="small"
        >
          Сохранить
        </Button>
      </Space>
    </div>
  );
}

export default function AppearanceModal({ open, current, onClose }: Props) {
  return (
    <Modal
      open={open}
      title="Цвета планировщика"
      onCancel={onClose}
      footer={null}
      width={400}
      destroyOnHidden
    >
      {open && <AppearanceModalContent initial={current} onClose={onClose} />}
    </Modal>
  );
}
