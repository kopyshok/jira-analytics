import { useEffect, useState } from 'react';
import { Card, Empty, Space, Spin, Tabs, Typography } from 'antd';
import teamDeskHelp from '../../../docs/help/team-desk.md?raw';
import { FLAG_LABELS, type DeskFilterPrefs, type FlagCode } from '../api/teamDesk';
import { useRegisterHelp } from '../contexts/HelpContext';
import {
  useDeskFilter, useDeskOverview, useDeskSettings, useSaveDeskFilter,
} from '../hooks/useTeamDesk';
import { useJiraBaseUrl } from '../hooks/useSettings';
import { DeskFilters } from '../components/teamdesk/DeskFilters';
import { ThresholdsPanel } from '../components/teamdesk/ThresholdsPanel';
import { DeveloperCards } from '../components/teamdesk/DeveloperCards';
import { DeveloperTable } from '../components/teamdesk/DeveloperTable';
import { GroupedIssues } from '../components/teamdesk/GroupedIssues';
import { FlagFilterBar } from '../components/teamdesk/FlagFilterBar';
import { WorkloadBars } from '../components/teamdesk/WorkloadBars';
import { AbsenceStrip } from '../components/teamdesk/AbsenceStrip';

type Layout = 'cards' | 'table' | 'grouped';
const LAYOUT_KEY = 'team-desk-layout';

export default function TeamDeskPage() {
  useRegisterHelp('Рабочий стол тимлида', teamDeskHelp);
  const [onlyOpen, setOnlyOpen] = useState(true);
  const [showReviewed, setShowReviewed] = useState(false);
  const [showThresholds, setShowThresholds] = useState(false);
  const [selectedDev, setSelectedDev] = useState<string | null>(null);
  const [flagFilter, setFlagFilter] = useState<FlagCode | null>(null);
  // Тимлид пробует все три раскладки и остаётся на удобной — переключать
  // её каждый вход он не должен.
  const [layout, setLayout] = useState<Layout>(
    () => (localStorage.getItem(LAYOUT_KEY) as Layout) || 'cards',
  );
  useEffect(() => localStorage.setItem(LAYOUT_KEY, layout), [layout]);

  // Команды и добранные люди живут в профиле: тимлид выбирает состав один раз,
  // и видит его с любого компьютера.
  const filterPrefs = useDeskFilter();
  const saveFilter = useSaveDeskFilter();
  // Пока тимлид ничего не трогал, показываем сохранённый в профиле выбор;
  // после первой правки главной становится правка на экране.
  const [picked, setPicked] = useState<DeskFilterPrefs | null>(null);
  const teams = picked?.teams ?? filterPrefs.data?.teams ?? [];
  const developers = picked?.developers ?? filterPrefs.data?.developers ?? [];

  const change = (next: DeskFilterPrefs) => {
    setPicked(next);
    saveFilter.mutate(next);
  };

  const settings = useDeskSettings();
  const jiraBaseUrl = useJiraBaseUrl().data?.base_url ?? '';
  const overview = useDeskOverview({ teams, developers, onlyOpen, showReviewed });
  const data = overview.data;
  const overrunPct = settings.data?.thresholds.overrun_pct ?? 30;
  const wipLimit = settings.data?.thresholds.wip_limit ?? 3;

  const hints = [
    selectedDev ? 'нажмите на карточку ещё раз, чтобы снять фильтр' : '',
    flagFilter ? `отфильтровано: ${FLAG_LABELS[flagFilter]}` : '',
  ].filter(Boolean);

  const detailBlocks = (
    <>
      <GroupedIssues
        title="Задачи"
        developers={data?.developers ?? []}
        issues={data?.issues ?? []}
        overrunPct={overrunPct}
        jiraBaseUrl={jiraBaseUrl}
        onlyDeveloper={selectedDev}
        flagFilter={flagFilter}
        hint={hints.join(' · ')}
      />
      <Card size="small" title="Задач в работе одновременно">
        <WorkloadBars
          developers={data?.developers ?? []}
          workload={data?.workload ?? {}}
          limit={wipLimit}
        />
      </Card>
    </>
  );

  return (
    <Space orientation="vertical" size={14} style={{ width: '100%' }}>
      <div>
        <Typography.Title level={4} style={{ margin: 0 }}>Рабочий стол тимлида</Typography.Title>
        <Typography.Text type="secondary">
          Контроль задач в разрезе разработчиков: где стоит, кто не укладывается в оценку,
          что не разбито на подзадачи.
        </Typography.Text>
      </div>

      <DeskFilters
        teams={teams}
        onTeamsChange={(value) => change({ teams: value, developers })}
        developers={developers}
        onDevelopersChange={(value) => change({ teams, developers: value })}
        developerRoles={settings.data?.developer_roles ?? ['dev']}
        onlyOpen={onlyOpen}
        onOnlyOpenChange={setOnlyOpen}
        showReviewed={showReviewed}
        onShowReviewedChange={setShowReviewed}
        onToggleThresholds={() => setShowThresholds((v) => !v)}
      />

      {showThresholds && settings.data && (
        <ThresholdsPanel
          key={JSON.stringify(settings.data.thresholds)}
          settings={settings.data}
        />
      )}

      <Tabs
        activeKey={layout}
        onChange={(key) => setLayout(key as Layout)}
        items={[
          { key: 'cards', label: 'Светофор' },
          { key: 'table', label: 'Ведомость' },
          { key: 'grouped', label: 'Проблемы вперёд' },
        ]}
      />

      {data && (
        <FlagFilterBar
          flagCounts={data.flag_counts}
          value={flagFilter}
          onChange={setFlagFilter}
        />
      )}

      {(overview.isLoading || filterPrefs.isLoading) && <Spin />}
      {!overview.isLoading && !filterPrefs.isLoading && !data && (
        <Empty description="Выберите команды или добавьте разработчиков" />
      )}

      {data && layout === 'cards' && (
        <>
          <DeveloperCards
            developers={data.developers}
            workload={data.workload}
            overrunPct={overrunPct}
            selected={selectedDev}
            onSelect={setSelectedDev}
          />
          {detailBlocks}
        </>
      )}

      {data && layout === 'table' && (
        <>
          <Card size="small" title="Сводка по разработчикам">
            <DeveloperTable
              developers={data.developers}
              workload={data.workload}
              overrunPct={overrunPct}
              selected={selectedDev}
              onSelect={setSelectedDev}
            />
          </Card>
          {detailBlocks}
        </>
      )}

      {data && layout === 'grouped' && (
        <GroupedIssues
          title="Задачи по разработчикам"
          developers={data.developers}
          issues={data.issues}
          overrunPct={overrunPct}
          jiraBaseUrl={jiraBaseUrl}
          scale="centered"
          flagFilter={flagFilter}
          hint={hints.join(' · ')}
        />
      )}

      {data && (
        <Card size="small" title="Отсутствия">
          <AbsenceStrip employeeIds={data.employee_ids ?? {}} />
        </Card>
      )}
    </Space>
  );
}
