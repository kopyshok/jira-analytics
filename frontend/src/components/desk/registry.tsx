import type { ComponentType } from 'react';
import MyTasksWidget from './MyTasksWidget';
import WeeklyLoadWidget from './WeeklyLoadWidget';
import MyConflictsWidget from './MyConflictsWidget';
import HoursBalanceWidget from './HoursBalanceWidget';
import UnloggedDaysWidget from './UnloggedDaysWidget';
import CategoryBreakdownWidget from './CategoryBreakdownWidget';
import TeamAbsencesWidget from './TeamAbsencesWidget';
import TeamAvailabilityWidget from './TeamAvailabilityWidget';
import ProductionCalendarWidget from './ProductionCalendarWidget';
import QuarterDeadlinesWidget from './QuarterDeadlinesWidget';
import ExternalHelpWidget from './ExternalHelpWidget';
import RecentChangesWidget from './RecentChangesWidget';

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
  my_tasks: { title: 'Мои задачи', component: MyTasksWidget, wide: true },
  weekly_load: { title: 'Загрузка по месяцам', component: WeeklyLoadWidget, wide: true },
  my_conflicts: { title: 'Мои конфликты', component: MyConflictsWidget },
  hours_balance: { title: 'Баланс часов', component: HoursBalanceWidget },
  unlogged_days: { title: 'Незаполненные дни', component: UnloggedDaysWidget },
  category_breakdown: { title: 'Часы по категориям', component: CategoryBreakdownWidget },
  team_absences: { title: 'Отсутствия команды', component: TeamAbsencesWidget },
  team_availability: { title: 'Занятость команды', component: TeamAvailabilityWidget },
  production_calendar: { title: 'Производственный календарь', component: ProductionCalendarWidget },
  quarter_deadlines: { title: 'Сроки квартала', component: QuarterDeadlinesWidget, wide: true },
  external_help: { title: 'Помощь другим командам', component: ExternalHelpWidget },
  recent_changes: { title: 'Недавние изменения', component: RecentChangesWidget },
};
