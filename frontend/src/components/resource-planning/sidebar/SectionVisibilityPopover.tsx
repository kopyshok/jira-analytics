import { Button, Checkbox, Popover, Space, Typography } from 'antd';
import { SettingOutlined } from '@ant-design/icons';

const LABELS: Record<string, string> = {
  algorithm: 'Откуда дата старта',
  day_table: 'Дни × часы',
  absences: 'Отсутствия в окне',
  sources: 'Часы по источникам',
  duration: 'Длительность vs часы',
  critical_path: 'Критический путь',
};

interface Props {
  visible: Record<string, boolean>;
  onChange: (next: Record<string, boolean>) => void;
}

export default function SectionVisibilityPopover({ visible, onChange }: Props) {
  return (
    <Popover
      trigger="click"
      placement="bottomRight"
      title="Показывать секции"
      content={
        <Space direction="vertical">
          {Object.entries(LABELS).map(([key, label]) => (
            <Checkbox
              key={key}
              checked={visible[key] !== false}
              onChange={(e) => onChange({ ...visible, [key]: e.target.checked })}
            >
              {label}
            </Checkbox>
          ))}
          <Typography.Text type="secondary" style={{ fontSize: 11 }}>
            Скрытые секции не отображаются. Свёрнутые можно развернуть в шапке секции.
          </Typography.Text>
        </Space>
      }
    >
      <Button icon={<SettingOutlined />} size="small" />
    </Popover>
  );
}
