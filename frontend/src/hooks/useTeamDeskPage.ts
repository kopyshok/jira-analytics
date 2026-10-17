import { useEffect, useState } from 'react';
import teamDeskHelp from '../../../docs/help/team-desk.md?raw';
import { orderedStatuses, type DeskFilterPrefs, type FlagCode } from '../api/teamDesk';
import { useGlobalTeamFilter } from './useGlobalTeamFilter';
import { useRegisterHelp } from '../contexts/HelpContext';
import {
  useDeskFilter, useDeskOverview, useDeskSettings, useRefreshDeskIssues,
  useSaveDailyRate, useSaveDeskFilter,
} from './useTeamDesk';
import { useJiraBaseUrl, useSyncBlocked } from './useSettings';
import type { QueueScope } from '../components/teamdesk/queueFilter';

export type DeskLayout = 'cards' | 'table' | 'grouped';
const LAYOUT_KEY = 'team-desk-layout';

/** Текущий квартал — период по умолчанию для режима «За период». */
function currentQuarter(): { start: string; end: string } {
  const now = new Date();
  const firstMonth = Math.floor(now.getMonth() / 3) * 3;
  const iso = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  return {
    start: iso(new Date(now.getFullYear(), firstMonth, 1)),
    end: iso(new Date(now.getFullYear(), firstMonth + 3, 0)),
  };
}

/**
 * Данные, состояние и действия «Рабочего стола тимлида» — общие для всех
 * раскладок (Aurora и обложки). Раскладки только рисуют.
 */
export function useTeamDeskPage() {
  useRegisterHelp('Рабочий стол тимлида', teamDeskHelp);
  // Команды у раздела свои, а группы приезжают из шапки: группа чужой команды
  // на сервере отбрасывается, срез от неё не пустеет.
  const { selectedSubgroups } = useGlobalTeamFilter();
  const [showThresholds, setShowThresholds] = useState(false);
  const [selectedDev, setSelectedDev] = useState<string | null>(null);
  const [flagFilter, setFlagFilter] = useState<FlagCode | null>(null);
  const [statusFilter, setStatusFilter] = useState<string | null>(null);
  // Какая строка очереди разложена по задачам: расшифровка живёт до
  // следующего клика, в профиле не сохраняется — это разовый разрез.
  const [queueScope, setQueueScope] = useState<QueueScope>(null);
  // Тимлид пробует все три раскладки и остаётся на удобной — переключать
  // её каждый вход он не должен.
  const [layout, setLayout] = useState<DeskLayout>(
    () => (localStorage.getItem(LAYOUT_KEY) as DeskLayout) || 'cards',
  );
  useEffect(() => localStorage.setItem(LAYOUT_KEY, layout), [layout]);

  // Вся шапка раздела живёт в профиле: тимлид настраивает вид один раз и
  // видит его при следующем заходе с любого компьютера.
  const filterPrefs = useDeskFilter();
  const saveFilter = useSaveDeskFilter();
  // Пока тимлид ничего не трогал, показываем сохранённый в профиле выбор;
  // после первой правки главной становится правка на экране.
  const [picked, setPicked] = useState<DeskFilterPrefs | null>(null);
  const quarter = currentQuarter();
  const prefs: DeskFilterPrefs = {
    teams: [], developers: [], mode: 'open',
    period_start: quarter.start, period_end: quarter.end,
    show_reviewed: false, show_done_subtasks: true, status_counters: [],
    hidden_columns: [], column_widths: {},
    group_by_developer: true, sprints: [], releases: [],
    ...(filterPrefs.data ?? {}),
    ...(picked ?? {}),
  };
  const { teams, developers } = prefs;
  const periodStart = prefs.period_start ?? quarter.start;
  const periodEnd = prefs.period_end ?? quarter.end;

  const change = (patch: Partial<DeskFilterPrefs>) => {
    const next = { ...prefs, ...patch };
    setPicked(next);
    saveFilter.mutate(next);
  };

  const settings = useDeskSettings();
  const jiraBaseUrl = useJiraBaseUrl().data?.base_url ?? '';
  const overview = useDeskOverview({
    teams,
    subgroups: selectedSubgroups,
    developers,
    mode: prefs.mode,
    periodStart,
    periodEnd,
    showReviewed: prefs.show_reviewed,
    showDoneSubtasks: prefs.show_done_subtasks,
  });
  const data = overview.data;
  const overrunPct = settings.data?.thresholds.overrun_pct ?? 30;
  const wipLimit = settings.data?.thresholds.wip_limit ?? 3;
  const rubberDays = settings.data?.thresholds.rubber_days ?? 5;
  const saveDailyRate = useSaveDailyRate();
  const setDailyRate = (issueId: string, hours: number | null) =>
    saveDailyRate.mutate({ issueId, hours });

  // Список статусов для настройки: те, по которым в срезе есть задачи, плюс
  // ранее выбранные — иначе выбор молча сбрасывался бы на пустом срезе.
  const seenStatuses = new Set<string>(prefs.status_counters);
  (data?.developers ?? []).forEach((dev) =>
    Object.keys(dev.status_counts ?? {}).forEach((s) => seenStatuses.add(s)));
  const statusGroups = settings.data?.status_groups;
  const statusOptions = orderedStatuses(statusGroups, seenStatuses);
  // Только для разрезов по разработчикам: плитки, ведомость, «проблемы вперёд».
  const shownStatuses = prefs.status_counters.length
    ? orderedStatuses(statusGroups, prefs.status_counters)
    : statusOptions;

  // Итог по срезу: задачи разбиты по владельцам, поэтому сумма по людям — это
  // и есть счётчик команды, без задвоений.
  const totalStatusCounts: Record<string, number> = {};
  (data?.developers ?? []).forEach((dev) =>
    Object.entries(dev.status_counts ?? {}).forEach(([status, count]) => {
      totalStatusCounts[status] = (totalStatusCounts[status] ?? 0) + count;
    }));

  // Варианты отбора собираем из самого среза: спринт и релиз приходят
  // вместе с задачами, отдельного справочника не нужно.
  const sprintOptions = Array.from(
    new Set((data?.issues ?? []).map((i) => i.sprint).filter(Boolean) as string[]),
  ).sort((a, b) => a.localeCompare(b, 'ru'));
  const releaseOptions = Array.from(
    new Set((data?.issues ?? []).map((i) => i.release).filter(Boolean) as string[]),
  ).sort((a, b) => a.localeCompare(b, 'ru'));

  const refreshIssues = useRefreshDeskIssues();
  const syncBlocked = useSyncBlocked();
  const refreshVisible = (keys: string[]) => {
    if (keys.length) refreshIssues.mutate(keys);
  };

  // Настройка рабочего места и кнопка обновления — общие для всех раскладок.
  const listProps = {
    hiddenColumns: prefs.hidden_columns,
    columnWidths: prefs.column_widths,
    onColumnWidthsChange: (widths: Record<string, number>) =>
      change({ column_widths: widths }),
    groupByDeveloper: prefs.group_by_developer,
    sprintFilter: prefs.sprints,
    releaseFilter: prefs.releases,
    onHiddenColumnsChange: (hidden: string[]) => change({ hidden_columns: hidden }),
    onGroupByDeveloperChange: (value: boolean) => change({ group_by_developer: value }),
    onRefreshVisible: refreshVisible,
    refreshing: refreshIssues.isPending,
    refreshBlocked: syncBlocked,
  };

  const pickStatus = (developerId: string, status: string | null) => {
    setSelectedDev(status ? developerId : null);
    setStatusFilter(status);
  };

  // Клик по строке очереди и по значку замечания на плитке: человек остаётся
  // выбранным и после снятия разреза — иначе экран прыгает обратно на всю команду.
  const pickQueue = (developerId: string, scope: QueueScope) => {
    setSelectedDev(developerId);
    setQueueScope(scope);
  };

  const pickFlag = (developerId: string, flag: FlagCode | null) => {
    setSelectedDev(developerId);
    setFlagFilter(flag);
  };

  const resetFilters = () => {
    setSelectedDev(null);
    setFlagFilter(null);
    setStatusFilter(null);
    setQueueScope(null);
  };

  // Разработчика сняли — фильтр по его статусу тоже снимается, иначе список
  // остался бы урезанным без видимой причины.
  const pickDeveloper = (id: string | null) => {
    setSelectedDev(id);
    if (!id) {
      setStatusFilter(null);
      setQueueScope(null);
    }
  };

  // Полоса статусов — фильтр на весь срез: выбор конкретного человека снимается.
  const pickSliceStatus = (status: string | null) => {
    setSelectedDev(null);
    setStatusFilter(status);
  };

  const selectedName = data?.developers.find(
    (dev) => dev.developer_id === selectedDev,
  )?.display_name;

  return {
    showThresholds, setShowThresholds,
    selectedDev, flagFilter, setFlagFilter, statusFilter, queueScope,
    layout, setLayout, filterPrefs, prefs, teams, developers, periodStart, periodEnd, change,
    settings, jiraBaseUrl, overview, data, overrunPct, wipLimit, rubberDays, setDailyRate,
    statusGroups, statusOptions, shownStatuses, totalStatusCounts,
    sprintOptions, releaseOptions, listProps,
    pickStatus, pickQueue, pickFlag, resetFilters, pickDeveloper, pickSliceStatus, selectedName,
  };
}

export type TeamDeskPageModel = ReturnType<typeof useTeamDeskPage>;
