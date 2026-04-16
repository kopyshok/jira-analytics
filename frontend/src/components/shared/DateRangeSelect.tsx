import { DatePicker, Space } from 'antd';
import type { Dayjs } from 'dayjs';

const { RangePicker } = DatePicker;

interface Props {
  value: [Dayjs | null, Dayjs | null] | null;
  onChange: (dates: [Dayjs | null, Dayjs | null] | null) => void;
}

export default function DateRangeSelect({ value, onChange }: Props) {
  return (
    <Space>
      <span>Период:</span>
      <RangePicker
        value={value as [Dayjs, Dayjs] | null}
        onChange={(dates) => onChange(dates as [Dayjs | null, Dayjs | null] | null)}
        format="DD.MM.YYYY"
      />
    </Space>
  );
}
