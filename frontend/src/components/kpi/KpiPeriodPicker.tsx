import { Button, InputNumber, Segmented, Select, Space, Tooltip, Typography } from 'antd';
import { LeftOutlined, RightOutlined } from '@ant-design/icons';
import {
  QUARTER_LABELS, modeOf, periodForMode, periodLabel, quarterOfMonth, stepPeriod,
  type KpiPeriod, type KpiPeriodMode,
} from '../../utils/kpiPeriod';

const { Text } = Typography;

const MODE_OPTIONS = [
  { value: 'month', label: 'Месяц' },
  { value: 'quarter', label: 'Квартал' },
  { value: 'last', label: 'Последние месяцы' },
  { value: 'custom', label: 'Свой период' },
];

interface Props {
  period: KpiPeriod;
  onChange: (next: KpiPeriod) => void;
}

/**
 * Выбор периода ведомости: месяц, конкретный квартал, последние N месяцев
 * или произвольный отрезок. Все режимы задают одно и то же — конечный месяц
 * и длину, — поэтому переключение между ними не теряет выбранную точку.
 */
export default function KpiPeriodPicker({ period, onChange }: Props) {
  const mode = modeOf(period);
  // «Последние месяцы» и «Свой период» описывают одинаковую пару чисел;
  // отличает их только то, что первый прижимает конец периода к текущему
  // месяцу. По этому признаку и решаем, какую кнопку подсветить.
  const now = new Date();
  const endsNow = period.year === now.getFullYear() && period.month === now.getMonth() + 1;
  const shownMode: KpiPeriodMode = mode === 'custom' && endsNow ? 'last' : mode;

  return (
    <Space wrap size="middle">
      <Segmented
        value={shownMode}
        options={MODE_OPTIONS}
        onChange={(value) => onChange(periodForMode(period, value as KpiPeriodMode))}
      />

      <Space size={4}>
        <Button
          icon={<LeftOutlined />}
          size="small"
          aria-label="Предыдущий период"
          onClick={() => onChange(stepPeriod(period, -1))}
        />
        <span style={{ minWidth: 190, textAlign: 'center', fontWeight: 600 }}>
          {periodLabel(period)}
        </span>
        <Button
          icon={<RightOutlined />}
          size="small"
          aria-label="Следующий период"
          onClick={() => onChange(stepPeriod(period, 1))}
        />
      </Space>

      {shownMode === 'quarter' && (
        <Select
          style={{ width: 180 }}
          value={quarterOfMonth(period.month)}
          onChange={(q) => onChange({ ...period, month: q * 3 })}
          options={QUARTER_LABELS.map((label, i) => ({ value: i + 1, label }))}
        />
      )}

      {(shownMode === 'last' || shownMode === 'custom') && (
        <Space size={6}>
          <Text type="secondary" style={{ fontSize: 12 }}>Месяцев:</Text>
          <Tooltip title="Сколько месяцев подряд входит в период, считая назад от показанного">
            <InputNumber
              min={2}
              max={24}
              style={{ width: 72 }}
              value={period.months}
              onChange={(value) => onChange({ ...period, months: Number(value) || 2 })}
            />
          </Tooltip>
        </Space>
      )}
    </Space>
  );
}
