import { Space, Input } from 'antd';

interface Props {
  urlParams: { employeeId?: string; workType?: string; category?: string; taskQ?: string };
  onChange: (next: { employeeId?: string; workType?: string; category?: string; taskQ?: string }) => void;
}

export default function AnalyticsFilters({ urlParams, onChange }: Props) {
  return (
    <Space wrap style={{ marginBottom: 12 }}>
      <Input.Search
        placeholder="Поиск задачи"
        defaultValue={urlParams.taskQ}
        onSearch={(v) => onChange({ ...urlParams, taskQ: v || undefined })}
        style={{ width: 240 }}
      />
      {/* Сотрудник / Вид работ / Категория — TODO в Task 14 */}
    </Space>
  );
}
