import type { ComponentType } from 'react';
import MyTasksWidget from './MyTasksWidget';
import MyTimelineWidget from './MyTimelineWidget';
import StaleTasksWidget from './StaleTasksWidget';
import HoursBalanceWidget from './HoursBalanceWidget';
import CategoryBreakdownWidget from './CategoryBreakdownWidget';
import TeamAbsencesWidget from './TeamAbsencesWidget';
import TeamAvailabilityWidget from './TeamAvailabilityWidget';
import ProductionCalendarWidget from './ProductionCalendarWidget';
import AwaitingReactionWidget from './AwaitingReactionWidget';

export interface WidgetProps {
  token: string;
  title: string;
}

interface WidgetDef {
  title: string;
  component: ComponentType<WidgetProps>;
  /** Виджеты с графиками/таблицами шире — занимают 2 колонки на больших экранах. */
  wide?: boolean;
}

/** Реестр виджетов стола. Порядок отображения — порядок ключей в enabled_widgets. */
export const WIDGET_REGISTRY: Record<string, WidgetDef> = {
  my_tasks: { title: 'Мои проекты', component: MyTasksWidget, wide: true },
  my_timeline: { title: 'Таймлайн моих проектов', component: MyTimelineWidget, wide: true },
  stale_tasks: { title: 'Залежавшиеся задачи', component: StaleTasksWidget, wide: true },
  hours_balance: { title: 'Переработка', component: HoursBalanceWidget },
  category_breakdown: { title: 'Часы по видам работ', component: CategoryBreakdownWidget },
  team_absences: { title: 'Отсутствия команды', component: TeamAbsencesWidget, wide: true },
  team_availability: { title: 'Занятость команды', component: TeamAvailabilityWidget, wide: true },
  production_calendar: { title: 'Производственный календарь', component: ProductionCalendarWidget, wide: true },
  awaiting_reaction: { title: 'Ждут моей реакции', component: AwaitingReactionWidget, wide: true },
};
