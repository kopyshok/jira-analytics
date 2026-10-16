import { Button, Card, DatePicker, Segmented, Select, Space, Switch, Typography } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import type { DeskMode } from '../../api/teamDesk';
import { useTeams } from '../../hooks/useSync';
import { useEmployees } from '../../hooks/useCapacity';

const DATE_FMT = 'YYYY-MM-DD';

interface Props {
  teams: string[];
  onTeamsChange: (v: string[]) => void;
  developers: string[];
  onDevelopersChange: (v: string[]) => void;
  /** Коды ролей, которые считаются разработчиками. */
  developerRoles: string[];
  mode: DeskMode;
  onModeChange: (v: DeskMode) => void;
  periodStart: string;
  periodEnd: string;
  onPeriodChange: (start: string, end: string) => void;
  showReviewed: boolean;
  onShowReviewedChange: (v: boolean) => void;
  showDoneSubtasks: boolean;
  onShowDoneSubtasksChange: (v: boolean) => void;
  onToggleThresholds: () => void;
  /** Спринты и релизы, встретившиеся в срезе — варианты для отбора. */
  sprintOptions: string[];
  releaseOptions: string[];
  sprints: string[];
  onSprintsChange: (v: string[]) => void;
  releases: string[];
  onReleasesChange: (v: string[]) => void;
  /** «panel» — органы в ряд с подписями над ними (обложка), без карточки. */
  variant?: 'card' | 'panel';
}

/** Шапка раздела: команды, добранные точечно люди, период, пороги. */
export function DeskFilters({
  teams, onTeamsChange,
  developers, onDevelopersChange, developerRoles,
  mode, onModeChange,
  periodStart, periodEnd, onPeriodChange,
  showReviewed, onShowReviewedChange,
  showDoneSubtasks, onShowDoneSubtasksChange,
  onToggleThresholds,
  sprintOptions, releaseOptions,
  sprints, onSprintsChange, releases, onReleasesChange,
  variant = 'card',
}: Props) {
  const teamsQuery = useTeams();
  const employeesQuery = useEmployees({ isActive: true });

  const teamsSelect = (
        <Select
          mode="multiple"
          allowClear
          placeholder="Выберите команды"
          style={{ flex: '2 1 180px', minWidth: 120 }}
          value={teams}
          onChange={onTeamsChange}
          loading={teamsQuery.isLoading}
          options={(teamsQuery.data ?? []).map((t) => ({ value: t, label: t }))}
          maxTagCount="responsive"
        />
  );
  const peopleSelect = (
        <Select
          mode="multiple"
          allowClear
          showSearch
          optionFilterProp="label"
          placeholder="Добрать разработчика"
          style={{ flex: '1 1 150px', minWidth: 120 }}
          value={developers}
          onChange={onDevelopersChange}
          loading={employeesQuery.isLoading}
          options={(employeesQuery.data ?? [])
            .filter((e) => e.role && developerRoles.includes(e.role))
            .map((e) => ({
              value: e.jira_account_id,
              label: e.display_name,
            }))}
          maxTagCount="responsive"
        />
  );
  const sprintSelect = (
        <Select
          mode="multiple"
          allowClear
          showSearch
          optionFilterProp="label"
          placeholder="Все спринты"
          style={{ flex: '1 1 140px', minWidth: 110 }}
          value={sprints}
          onChange={onSprintsChange}
          options={sprintOptions.map((v) => ({ value: v, label: v }))}
          maxTagCount="responsive"
        />
  );
  const releaseSelect = (
        <Select
          mode="multiple"
          allowClear
          showSearch
          optionFilterProp="label"
          placeholder="Все релизы"
          style={{ flex: '1 1 140px', minWidth: 110 }}
          value={releases}
          onChange={onReleasesChange}
          options={releaseOptions.map((v) => ({ value: v, label: v }))}
          maxTagCount="responsive"
        />
  );
  const modeSwitch = (
        <Segmented
          style={{ flexShrink: 0 }}
          value={mode}
          onChange={(v) => onModeChange(v as DeskMode)}
          options={[
            { value: 'open', label: 'Открытые сейчас' },
            { value: 'period', label: 'За период' },
            { value: 'all', label: 'Все задачи' },
          ]}
        />
  );
  const periodPicker = mode === 'period' && (
          <DatePicker.RangePicker
            style={{ flexShrink: 0 }}
            value={[dayjs(periodStart), dayjs(periodEnd)]}
            onChange={(range) => {
              if (range?.[0] && range?.[1]) {
                onPeriodChange(range[0].format(DATE_FMT), range[1].format(DATE_FMT));
              }
            }}
            allowClear={false}
            format="DD.MM.YYYY"
          />
  );
  const reviewedSwitch = (
        <Space size={6} style={{ flexShrink: 0 }}>
          <Switch size="small" checked={showReviewed} onChange={onShowReviewedChange} />
          <Typography.Text type="secondary" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
            показывать просмотренные
          </Typography.Text>
        </Space>
  );
  const subtasksSwitch = (
        <Space size={6} style={{ flexShrink: 0 }}>
          <Switch
            size="small"
            checked={showDoneSubtasks}
            onChange={onShowDoneSubtasksChange}
            // В режиме «все задачи» закрытые подзадачи видны и без тумблера.
            disabled={mode === 'all'}
          />
          <Typography.Text
            type="secondary"
            style={{ fontSize: 12 }}
            title="Показывать закрытые подзадачи под их родителями — видно, разбита задача или нет"
          >
            выполненные подзадачи
          </Typography.Text>
        </Space>
  );
  const settingsButton = (
        <Button icon={<SettingOutlined />} onClick={onToggleThresholds} title="Настройки вида" />
  );

  if (variant === 'panel') {
    return (
      <div className="pc-row td-filters">
        <label className="pc-field td-f-teams"><span className="pc-cap">Команды</span>{teamsSelect}</label>
        <label className="pc-field td-f-people"><span className="pc-cap">Отдельные люди</span>{peopleSelect}</label>
        <label className="pc-field td-f-sprint"><span className="pc-cap">Спринт</span>{sprintSelect}</label>
        <label className="pc-field td-f-release"><span className="pc-cap">Релиз</span>{releaseSelect}</label>
        <div className="pc-field"><span className="pc-cap">Режим</span>{modeSwitch}</div>
        {periodPicker && <div className="pc-field"><span className="pc-cap">Период</span>{periodPicker}</div>}
        <div className="pc-field td-f-switch"><span className="pc-cap">Просмотренные</span>{reviewedSwitch}</div>
        <div className="pc-field td-f-switch"><span className="pc-cap">Подзадачи</span>{subtasksSwitch}</div>
        <span className="pc-push td-f-settings">{settingsButton}</span>
      </div>
    );
  }

  return (
    <Card size="small" styles={{ body: { padding: '10px 12px' } }}>
      {/* Отборы жмутся под ширину окна и держатся в одну строку: выпадающие
          списки ужимаются, а не переносят шапку на второй ряд. */}
      <div
        style={{
          display: 'flex', flexWrap: 'wrap', alignItems: 'center',
          columnGap: 10, rowGap: 8, width: '100%',
        }}
      >
        <Typography.Text type="secondary" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>КОМАНДЫ</Typography.Text>
        {teamsSelect}

        <Typography.Text type="secondary" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>ОТДЕЛЬНЫЕ ЛЮДИ</Typography.Text>
        {peopleSelect}

        <Typography.Text type="secondary" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>СПРИНТ</Typography.Text>
        {sprintSelect}

        <Typography.Text type="secondary" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>РЕЛИЗ</Typography.Text>
        {releaseSelect}

        {modeSwitch}

        {periodPicker}

        {reviewedSwitch}

        {subtasksSwitch}

        {settingsButton}
      </div>
    </Card>
  );
}
