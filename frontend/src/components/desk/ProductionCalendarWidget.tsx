import { Progress, Statistic } from 'antd';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { CHART_COLORS } from '../../utils/constants';
import type { ProductionCalendarData } from '../../types/desk';

export default function ProductionCalendarWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<ProductionCalendarData>(
    token,
    'production_calendar',
  );
  const total = data?.quarter_workdays ?? 0;
  const remaining = data?.remaining_workdays ?? 0;
  const passed = Math.max(0, total - remaining);
  const pct = total > 0 ? Math.round((passed / total) * 100) : 0;

  return (
    <WidgetShell title={title} isLoading={isLoading} isError={isError} isEmpty={total === 0}>
      <Statistic
        title="Осталось рабочих дней в квартале"
        value={remaining}
        suffix={`/ ${total}`}
        valueStyle={{ color: CHART_COLORS.cyan }}
      />
      <Progress
        percent={pct}
        strokeColor={CHART_COLORS.cyan}
        style={{ marginTop: 12 }}
        format={(p) => `пройдено ${p}%`}
      />
    </WidgetShell>
  );
}
