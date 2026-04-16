import { useSearchParams } from 'react-router';
import { Space, Select, InputNumber } from 'antd';
import { useQuarterYear } from '../../hooks/useQuarterYear';

export default function QuarterYearSelect() {
  const [params, setParams] = useSearchParams();
  const { year, quarter } = useQuarterYear();

  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    next.set(key, value);
    setParams(next);
  };

  return (
    <Space>
      <span>Год:</span>
      <InputNumber
        value={Number(year)}
        min={2020}
        max={2030}
        onChange={(v) => v && update('year', String(v))}
        style={{ width: 100 }}
      />
      <span>Квартал:</span>
      <Select
        value={quarter}
        onChange={(v) => update('quarter', v)}
        style={{ width: 80 }}
        options={[
          { value: '1', label: 'Q1' },
          { value: '2', label: 'Q2' },
          { value: '3', label: 'Q3' },
          { value: '4', label: 'Q4' },
        ]}
      />
    </Space>
  );
}
