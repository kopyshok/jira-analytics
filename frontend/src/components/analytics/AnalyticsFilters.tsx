import { Space, Input, Select } from 'antd';
import { Search } from 'lucide-react';
import { useEmployeesForFilter } from '../../hooks/useAnalytics';
import { useCategories } from '../../hooks/useCategories';
import { useMandatoryWorkTypes } from '../../hooks/useMandatoryWorkTypes';

interface Props {
  urlParams: { employeeId?: string; workType?: string; category?: string; taskQ?: string };
  onChange: (next: { employeeId?: string; workType?: string; category?: string; taskQ?: string }) => void;
  /** Вид скина: подпись внутри поля («Сотрудник: все»), поиск с лупой слева, поля 40 px. */
  compact?: boolean;
}

export default function AnalyticsFilters({ urlParams, onChange, compact = false }: Props) {
  const { data: employees = [] } = useEmployeesForFilter();
  const { items: categories } = useCategories();
  const { data: workTypes = [] } = useMandatoryWorkTypes();

  const employeeOptions = employees.map((e) => ({ value: e.id, label: e.display_name }));
  const categoryOptions = categories.map((c) => ({ value: c.code, label: c.label }));
  const workTypeOptions = workTypes.map((w) => ({ value: w.code, label: w.label }));

  if (compact) {
    return (
      <div className="anc-filters" role="group" aria-label="Фильтры">
        <Select
          allowClear
          showSearch
          optionFilterProp="label"
          aria-label="Сотрудник"
          prefix="Сотрудник:"
          placeholder="все"
          className="anc-filter is-employee"
          popupMatchSelectWidth={280}
          options={employeeOptions}
          value={urlParams.employeeId ?? null}
          onChange={(v) => onChange({ ...urlParams, employeeId: v ?? undefined })}
        />
        <Input
          allowClear
          aria-label="Поиск задачи"
          placeholder="Поиск задачи"
          prefix={<Search size={16} aria-hidden />}
          className="anc-filter is-search"
          defaultValue={urlParams.taskQ}
          // Как у поиска Aurora: ищем по Enter; очистка поля снимает отбор сразу.
          onPressEnter={(e) => onChange({ ...urlParams, taskQ: e.currentTarget.value || undefined })}
          onChange={(e) => {
            if (!e.target.value && urlParams.taskQ) onChange({ ...urlParams, taskQ: undefined });
          }}
        />
        <Select
          allowClear
          showSearch
          optionFilterProp="label"
          aria-label="Вид работ"
          prefix="Вид работ:"
          placeholder="все"
          className="anc-filter is-work-type"
          popupMatchSelectWidth={260}
          options={workTypeOptions}
          value={urlParams.workType ?? null}
          onChange={(v) => onChange({ ...urlParams, workType: v ?? undefined })}
        />
        <Select
          allowClear
          showSearch
          optionFilterProp="label"
          aria-label="Категория"
          prefix="Категория:"
          placeholder="все"
          className="anc-filter is-category"
          popupMatchSelectWidth={260}
          options={categoryOptions}
          value={urlParams.category ?? null}
          onChange={(v) => onChange({ ...urlParams, category: v ?? undefined })}
        />
      </div>
    );
  }

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
