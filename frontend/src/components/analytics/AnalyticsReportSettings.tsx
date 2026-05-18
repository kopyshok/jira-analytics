import { Modal, Checkbox } from 'antd';
import type { CheckboxGroupProps } from 'antd/es/checkbox';
import { useAnalyticsColumns } from '../../hooks/useAnalyticsColumns';
import GroupingEditor from './GroupingEditor';

const COLUMN_LABELS: Record<string, string> = {
  plan_hours: 'Часы план',
  pct_plan: '% план',
  pct_total: '% от итога',
  worklog_count: 'Ворклогов',
  issue_count: 'Задач',
  employee_count: 'Сотрудников',
  avg_worklog_minutes: 'Ср. минут',
};

const CONFIGURABLE_COLUMNS = Object.keys(COLUMN_LABELS);

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function AnalyticsReportSettings({ open, onClose }: Props) {
  const { visible, setVisible } = useAnalyticsColumns();

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
      <h4 style={{ marginTop: 0, color: '#e6edf7' }}>Группировка</h4>
      <GroupingEditor />

      <div style={{ height: 1, background: 'rgba(255,255,255,0.06)', margin: '20px 0' }} />

      <h4 style={{ color: '#e6edf7' }}>Столбцы</h4>
      <Checkbox.Group
        options={options}
        value={currentChecked}
        onChange={handleChange}
        style={{ display: 'flex', flexDirection: 'column', gap: 8 }}
      />
    </Modal>
  );
}
