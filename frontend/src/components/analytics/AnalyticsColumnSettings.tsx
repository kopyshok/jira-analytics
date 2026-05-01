import { Modal, Checkbox } from 'antd';
import type { CheckboxGroupProps } from 'antd/es/checkbox';
import { useAnalyticsColumns } from '../../hooks/useAnalyticsColumns';

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

export default function AnalyticsColumnSettings({ open, onClose }: Props) {
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
      title="Настройка столбцов"
      open={open}
      onCancel={onClose}
      footer={null}
    >
      <Checkbox.Group
        options={options}
        value={currentChecked}
        onChange={handleChange}
        style={{ display: 'flex', flexDirection: 'column', gap: 8 }}
      />
    </Modal>
  );
}
