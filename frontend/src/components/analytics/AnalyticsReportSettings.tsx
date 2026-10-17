import { Modal, Checkbox } from 'antd';
import type { CheckboxGroupProps } from 'antd/es/checkbox';
import { CONFIGURABLE_COLUMN_LABELS as COLUMN_LABELS, useAnalyticsColumns } from '../../hooks/useAnalyticsColumns';
import { useAnalyticsLayout } from '../../hooks/useAnalyticsLayout';
import GroupingEditor from './GroupingEditor';

const CONFIGURABLE_COLUMNS = Object.keys(COLUMN_LABELS);

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function AnalyticsReportSettings({ open, onClose }: Props) {
  const { visible, setVisible } = useAnalyticsColumns();
  const { layout, resolved, save, isSaving } = useAnalyticsLayout();

  const options: CheckboxGroupProps['options'] = CONFIGURABLE_COLUMNS.map((col) => ({
    label: COLUMN_LABELS[col],
    value: col,
  }));

  const currentChecked = visible.filter((col) => CONFIGURABLE_COLUMNS.includes(col));

  const handleChange = (checked: string[]) => {
    const nonConfigurable = visible.filter((col) => !CONFIGURABLE_COLUMNS.includes(col));
    setVisible([...nonConfigurable, ...checked]);
  };

  return (
    <Modal
      title="Настройка отчёта"
      open={open}
      onCancel={onClose}
      footer={null}
    >
      <h4 style={{ marginTop: 0, color: 'var(--text, #e6edf7)' }}>Группировка</h4>
      <GroupingEditor />

      <div style={{ height: 1, background: 'var(--hairline, rgba(255,255,255,0.06))', margin: '20px 0' }} />

      <h4 style={{ color: 'var(--text, #e6edf7)' }}>Столбцы</h4>
      <Checkbox.Group
        options={options}
        value={currentChecked}
        onChange={handleChange}
        style={{ display: 'flex', flexDirection: 'column', gap: 8 }}
      />

      <div style={{ height: 1, background: 'var(--hairline, rgba(255,255,255,0.06))', margin: '20px 0' }} />

      <h4 style={{ color: 'var(--text, #e6edf7)' }}>Визуализация</h4>
      <Checkbox
        checked={resolved.showFactBar}
        disabled={isSaving}
        onChange={(e) =>
          save({ ...layout, show_fact_bar: e.target.checked })
        }
      >
        Полоска заполнения в колонке «Часы факт»
      </Checkbox>
    </Modal>
  );
}
