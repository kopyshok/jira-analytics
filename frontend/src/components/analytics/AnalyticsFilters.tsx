import { Space, Input, Select } from 'antd';
import { useEmployeesForFilter } from '../../hooks/useAnalytics';
import { useCategories } from '../../hooks/useCategories';
import { useMandatoryWorkTypes } from '../../hooks/useMandatoryWorkTypes';

interface Props {
  urlParams: { employeeId?: string; workType?: string; category?: string; taskQ?: string };
  onChange: (next: { employeeId?: string; workType?: string; category?: string; taskQ?: string }) => void;
  /** row — строкой над таблицей (Aurora); stack — сеткой с подписями в паспорте экрана (обложки). */
  variant?: 'row' | 'stack';
}

export default function AnalyticsFilters({ urlParams, onChange, variant = 'row' }: Props) {
  const { data: employees = [] } = useEmployeesForFilter();
  const { items: categories } = useCategories();
  const { data: workTypes = [] } = useMandatoryWorkTypes();
  const stack = variant === 'stack';
  const fieldVariant = stack ? ('underlined' as const) : undefined;

  const employeeOptions = employees.map((e) => ({ value: e.id, label: e.display_name }));
  const categoryOptions = categories.map((c) => ({ value: c.code, label: c.label }));
  const workTypeOptions = workTypes.map((w) => ({ value: w.code, label: w.label }));

  const employeeSelect = (
    <Select
      allowClear
      showSearch
      optionFilterProp="label"
      variant={fieldVariant}
      placeholder={stack ? 'Все' : 'Сотрудник'}
      style={stack ? undefined : { width: 200 }}
      options={employeeOptions}
      value={urlParams.employeeId ?? null}
      onChange={(v) => onChange({ ...urlParams, employeeId: v ?? undefined })}
    />
  );
  const taskSearch = (
    <Input.Search
      variant={fieldVariant}
      placeholder={stack ? 'Ключ или название' : 'Поиск задачи'}
      defaultValue={urlParams.taskQ}
      onSearch={(v) => onChange({ ...urlParams, taskQ: v || undefined })}
      style={stack ? undefined : { width: 240 }}
    />
  );
  const workTypeSelect = (
    <Select
      allowClear
      showSearch
      optionFilterProp="label"
      variant={fieldVariant}
      placeholder={stack ? 'Все' : 'Вид работ'}
      style={stack ? undefined : { width: 180 }}
      options={workTypeOptions}
      value={urlParams.workType ?? null}
      onChange={(v) => onChange({ ...urlParams, workType: v ?? undefined })}
    />
  );
  const categorySelect = (
    <Select
      allowClear
      showSearch
      optionFilterProp="label"
      variant={fieldVariant}
      placeholder={stack ? 'Все' : 'Категория'}
      style={stack ? undefined : { width: 180 }}
      options={categoryOptions}
      value={urlParams.category ?? null}
      onChange={(v) => onChange({ ...urlParams, category: v ?? undefined })}
    />
  );

  if (stack) {
    return (
      <div className="sw-field-row an-filters-stack">
        <div className="sw-field"><div className="sw-field-label">Сотрудник</div>{employeeSelect}</div>
        <div className="sw-field"><div className="sw-field-label">Вид работ</div>{workTypeSelect}</div>
        <div className="sw-field"><div className="sw-field-label">Категория</div>{categorySelect}</div>
        <div className="sw-field"><div className="sw-field-label">Поиск задачи</div>{taskSearch}</div>
      </div>
    );
  }

  return (
    <Space wrap style={{ marginBottom: 12 }}>
      {employeeSelect}
      {taskSearch}
      {workTypeSelect}
      {categorySelect}
    </Space>
  );
}
