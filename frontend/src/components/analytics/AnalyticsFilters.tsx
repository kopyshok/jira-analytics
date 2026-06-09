import { Space, Input, Select } from 'antd';
import { useEmployeesForFilter } from '../../hooks/useAnalytics';
import { useCategories } from '../../hooks/useCategories';
import { useMandatoryWorkTypes } from '../../hooks/useMandatoryWorkTypes';

interface Props {
  urlParams: { employeeId?: string; workType?: string; category?: string; taskQ?: string };
  onChange: (next: { employeeId?: string; workType?: string; category?: string; taskQ?: string }) => void;
}

export default function AnalyticsFilters({ urlParams, onChange }: Props) {
  const { data: employees = [] } = useEmployeesForFilter();
  const { items: categories } = useCategories();
  const { data: workTypes = [] } = useMandatoryWorkTypes();

  const employeeOptions = employees.map((e) => ({ value: e.id, label: e.display_name }));
  const categoryOptions = categories.map((c) => ({ value: c.code, label: c.label }));
  const workTypeOptions = workTypes.map((w) => ({ value: w.code, label: w.label }));

  return (
    <Space wrap style={{ marginBottom: 12 }}>
      <Select
        allowClear
        showSearch
        optionFilterProp="label"
        placeholder="Сотрудник"
        style={{ width: 200 }}
        options={employeeOptions}
        value={urlParams.employeeId ?? null}
        onChange={(v) => onChange({ ...urlParams, employeeId: v ?? undefined })}
      />
      <Input.Search
        placeholder="Поиск задачи"
        defaultValue={urlParams.taskQ}
        onSearch={(v) => onChange({ ...urlParams, taskQ: v || undefined })}
        style={{ width: 240 }}
      />
      <Select
        allowClear
        showSearch
        optionFilterProp="label"
        placeholder="Вид работ"
        style={{ width: 180 }}
        options={workTypeOptions}
        value={urlParams.workType ?? null}
        onChange={(v) => onChange({ ...urlParams, workType: v ?? undefined })}
      />
      <Select
        allowClear
        showSearch
        optionFilterProp="label"
        placeholder="Категория"
        style={{ width: 180 }}
        options={categoryOptions}
        value={urlParams.category ?? null}
        onChange={(v) => onChange({ ...urlParams, category: v ?? undefined })}
      />
    </Space>
  );
}
