import { Space, Input, Select } from 'antd';
import { BandField } from '../../skins/zones/ZonesBand';
import { useEmployeesForFilter } from '../../hooks/useAnalytics';
import { useCategories } from '../../hooks/useCategories';
import { useMandatoryWorkTypes } from '../../hooks/useMandatoryWorkTypes';

interface Props {
  urlParams: { employeeId?: string; workType?: string; category?: string; taskQ?: string };
  onChange: (next: { employeeId?: string; workType?: string; category?: string; taskQ?: string }) => void;
  /** «fields» — подписанные поля в ряд (скин «Цветовые зоны»). */
  variant?: 'default' | 'fields';
}

export default function AnalyticsFilters({ urlParams, onChange, variant = 'default' }: Props) {
  const { data: employees = [] } = useEmployeesForFilter();
  const { items: categories } = useCategories();
  const { data: workTypes = [] } = useMandatoryWorkTypes();

  const employeeOptions = employees.map((e) => ({ value: e.id, label: e.display_name }));
  const categoryOptions = categories.map((c) => ({ value: c.code, label: c.label }));
  const workTypeOptions = workTypes.map((w) => ({ value: w.code, label: w.label }));

  if (variant === 'fields') {
    return (
      <div className="an-filter-fields">
        <BandField label="Сотрудник" className="zn-field-bordered">
          <Select
            allowClear
            showSearch
            variant="borderless"
            optionFilterProp="label"
            placeholder="Все"
            style={{ width: 120 }}
            popupMatchSelectWidth={false}
            options={employeeOptions}
            value={urlParams.employeeId ?? null}
            onChange={(v) => onChange({ ...urlParams, employeeId: v ?? undefined })}
          />
        </BandField>
        <Input.Search
          className="an-search"
          placeholder="Поиск задачи"
          defaultValue={urlParams.taskQ}
          onSearch={(v) => onChange({ ...urlParams, taskQ: v || undefined })}
          style={{ width: 200 }}
        />
        <BandField label="Вид работ" className="zn-field-bordered">
          <Select
            allowClear
            showSearch
            variant="borderless"
            optionFilterProp="label"
            placeholder="Все"
            style={{ width: 110 }}
            popupMatchSelectWidth={false}
            options={workTypeOptions}
            value={urlParams.workType ?? null}
            onChange={(v) => onChange({ ...urlParams, workType: v ?? undefined })}
          />
        </BandField>
        <BandField label="Категория" className="zn-field-bordered">
          <Select
            allowClear
            showSearch
            variant="borderless"
            optionFilterProp="label"
            placeholder="Все"
            style={{ width: 110 }}
            popupMatchSelectWidth={false}
            options={categoryOptions}
            value={urlParams.category ?? null}
            onChange={(v) => onChange({ ...urlParams, category: v ?? undefined })}
          />
        </BandField>
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
