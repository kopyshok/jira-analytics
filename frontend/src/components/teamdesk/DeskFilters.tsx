import { Button, Card, Checkbox, DatePicker, Segmented, Select, Space, Switch, Typography } from 'antd';
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
  /** bar — строкой над вкладками (Aurora); stack — столбиком в паспорте экрана (обложки). */
  variant?: 'bar' | 'stack';
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
  variant = 'bar',
}: Props) {
  const teamsQuery = useTeams();
  const employeesQuery = useEmployees({ isActive: true });
  const stack = variant === 'stack';
  // Поля одни и те же в обеих раскладках: в паспорте — линией снизу и во всю ширину.
  const fieldVariant = stack ? ('underlined' as const) : undefined;
  const flexStyle = (flex: string, minWidth: number) => (stack ? undefined : { flex, minWidth });

  const teamsSelect = (
    <Select
      mode="multiple"
      allowClear
      variant={fieldVariant}
      placeholder="Выберите команды"
      style={flexStyle('2 1 180px', 120)}
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
      variant={fieldVariant}
      optionFilterProp="label"
      placeholder="Добрать разработчика"
      style={flexStyle('1 1 150px', 120)}
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
      variant={fieldVariant}
      optionFilterProp="label"
      placeholder="Все спринты"
      style={flexStyle('1 1 140px', 110)}
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
      variant={fieldVariant}
      optionFilterProp="label"
      placeholder="Все релизы"
      style={flexStyle('1 1 140px', 110)}
      value={releases}
      onChange={onReleasesChange}
      options={releaseOptions.map((v) => ({ value: v, label: v }))}
      maxTagCount="responsive"
    />
  );
  const modeSwitch = (
    <Segmented
      block={stack}
      style={stack ? undefined : { flexShrink: 0 }}
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
      variant={fieldVariant}
      style={stack ? undefined : { flexShrink: 0 }}
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
  const doneSubtasksHint = 'Показывать закрытые подзадачи под их родителями — видно, разбита задача или нет';
  const settingsButton = (
    <Button
      size={stack ? 'small' : undefined}
      icon={<SettingOutlined />}
      onClick={onToggleThresholds}
      title="Настройки вида"
      aria-label={stack ? 'Настройки вида' : undefined}
    />
  );

  if (stack) {
    return (
      <div className="desk-filters-stack">
        <div className="sw-field"><div className="sw-field-label">Команды</div>{teamsSelect}</div>
        <div className="sw-field"><div className="sw-field-label">Отдельные люди</div>{peopleSelect}</div>
        <div className="sw-field-row">
          <div className="sw-field"><div className="sw-field-label">Спринт</div>{sprintSelect}</div>
          <div className="sw-field"><div className="sw-field-label">Релиз</div>{releaseSelect}</div>
        </div>
        <div className="sw-field"><div className="sw-field-label">Режим</div>{modeSwitch}</div>
        {periodPicker && <div className="sw-field"><div className="sw-field-label">Период</div>{periodPicker}</div>}
        <div className="sw-checks">
          <Checkbox checked={showReviewed} onChange={(e) => onShowReviewedChange(e.target.checked)}>
            показывать просмотренные
          </Checkbox>
          <Checkbox
            checked={showDoneSubtasks}
            onChange={(e) => onShowDoneSubtasksChange(e.target.checked)}
            // В режиме «все задачи» закрытые подзадачи видны и без переключателя.
            disabled={mode === 'all'}
            title={doneSubtasksHint}
          >
            выполненные подзадачи
          </Checkbox>
          {settingsButton}
        </div>
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

        <Space size={6} style={{ flexShrink: 0 }}>
          <Switch size="small" checked={showReviewed} onChange={onShowReviewedChange} />
          <Typography.Text type="secondary" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>
            показывать просмотренные
          </Typography.Text>
        </Space>

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
            title={doneSubtasksHint}
          >
            выполненные подзадачи
          </Typography.Text>
        </Space>

        {settingsButton}
      </div>
    </Card>
  );
}
