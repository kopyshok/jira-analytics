import { Button, Card, DatePicker, Segmented, Select, Space, Switch, Typography } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import type { DeskMode } from '../../api/teamDesk';
import { useTeams } from '../../hooks/useSync';
import { useEmployees } from '../../hooks/useCapacity';

const DATE_FMT = 'YYYY-MM-DD';

/**
 * Подпись «ещё N» у списка, где метки не влезли. Пока скрытых меток нет,
 * AntD всё равно держит в разметке прозрачный замер «+ 0 ...» — его текст
 * читают экранные дикторы и проверка контраста; пустая подпись их не путает.
 */
const restTags = (omitted: unknown[]) => (omitted.length ? `+${omitted.length}` : '');

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
  /**
   * Компактный вид скина: поля с подписью внутри рамки, две строки, без
   * своей карточки. `trailing` — элемент в конце второй строки (шестерёнка
   * с панелью настроек); не задан — обычная шестерёнка.
   */
  compact?: boolean;
  trailing?: React.ReactNode;
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
  compact = false, trailing,
}: Props) {
  const teamsQuery = useTeams();
  const employeesQuery = useEmployees({ isActive: true });

  if (compact) {
    const field = (id: string, label: string, control: React.ReactNode, cls: string) => (
      <div className={`wr-field tdc-field ${cls}`}>
        <label className="wr-field-label" htmlFor={id}>{label}</label>
        {control}
      </div>
    );
    return (
      <div className="tdc-filters" role="group" aria-label="Фильтры">
        <div className="tdc-filters-row">
          {field('tdc-teams', 'Команды', (
            <Select
              id="tdc-teams"
              variant="borderless"
              mode="multiple"
              allowClear
              placeholder="Выберите команды"
              value={teams}
              onChange={onTeamsChange}
              loading={teamsQuery.isLoading}
              options={(teamsQuery.data ?? []).map((t) => ({ value: t, label: t }))}
              maxTagCount="responsive"
              maxTagPlaceholder={restTags}
              popupMatchSelectWidth={false}
            />
          ), 'is-teams')}
          {field('tdc-people', 'Отдельные люди', (
            <Select
              id="tdc-people"
              variant="borderless"
              mode="multiple"
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder="Добрать разработчика"
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
              maxTagPlaceholder={restTags}
              popupMatchSelectWidth={false}
            />
          ), 'is-people')}
          {field('tdc-sprint', 'Спринт', (
            <Select
              id="tdc-sprint"
              variant="borderless"
              mode="multiple"
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder="Все спринты"
              value={sprints}
              onChange={onSprintsChange}
              options={sprintOptions.map((v) => ({ value: v, label: v }))}
              maxTagCount="responsive"
              maxTagPlaceholder={restTags}
              popupMatchSelectWidth={false}
            />
          ), 'is-sprint')}
          {field('tdc-release', 'Релиз', (
            <Select
              id="tdc-release"
              variant="borderless"
              mode="multiple"
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder="Все релизы"
              value={releases}
              onChange={onReleasesChange}
              options={releaseOptions.map((v) => ({ value: v, label: v }))}
              maxTagCount="responsive"
              maxTagPlaceholder={restTags}
              popupMatchSelectWidth={false}
            />
          ), 'is-release')}
          <Segmented
            className="tdc-seg"
            aria-label="Режим"
            value={mode}
            onChange={(v) => onModeChange(v as DeskMode)}
            options={[
              { value: 'open', label: 'Открытые сейчас' },
              { value: 'period', label: 'За период' },
              { value: 'all', label: 'Все задачи' },
            ]}
          />
          <label className="tdc-switch">
            <Switch checked={showReviewed} onChange={onShowReviewedChange} aria-label="Показывать просмотренные" />
            <span>показывать просмотренные</span>
          </label>
        </div>
        <div className="tdc-filters-row">
          <label
            className="tdc-switch"
            title="Показывать закрытые подзадачи под их родителями — видно, разбита задача или нет"
          >
            <Switch
              checked={showDoneSubtasks}
              onChange={onShowDoneSubtasksChange}
              // В режиме «все задачи» закрытые подзадачи видны и без тумблера.
              disabled={mode === 'all'}
              aria-label="Выполненные подзадачи"
            />
            <span>выполненные подзадачи</span>
          </label>
          {mode === 'period' && (
            <div className="wr-field tdc-field">
              <span className="wr-field-label">Период</span>
              <DatePicker.RangePicker
                variant="borderless"
                value={[dayjs(periodStart), dayjs(periodEnd)]}
                onChange={(range) => {
                  if (range?.[0] && range?.[1]) {
                    onPeriodChange(range[0].format(DATE_FMT), range[1].format(DATE_FMT));
                  }
                }}
                allowClear={false}
                format="DD.MM.YYYY"
              />
            </div>
          )}
          <span className="tdc-filters-end">
            {trailing ?? (
              <Button icon={<SettingOutlined />} onClick={onToggleThresholds} title="Настройки вида" aria-label="Настройки вида" />
            )}
          </span>
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

        <Typography.Text type="secondary" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>ОТДЕЛЬНЫЕ ЛЮДИ</Typography.Text>
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

        <Typography.Text type="secondary" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>СПРИНТ</Typography.Text>
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

        <Typography.Text type="secondary" style={{ fontSize: 12, whiteSpace: 'nowrap' }}>РЕЛИЗ</Typography.Text>
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

        {mode === 'period' && (
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
        )}

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
            title="Показывать закрытые подзадачи под их родителями — видно, разбита задача или нет"
          >
            выполненные подзадачи
          </Typography.Text>
        </Space>

        <Button icon={<SettingOutlined />} onClick={onToggleThresholds} title="Настройки вида" />
      </div>
    </Card>
  );
}
