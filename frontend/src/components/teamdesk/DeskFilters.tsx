import { Button, Card, DatePicker, Segmented, Select, Space, Switch, Typography } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import type { DeskMode } from '../../api/teamDesk';
import { useTeams } from '../../hooks/useSync';
import { useEmployees } from '../../hooks/useCapacity';
import { BandField } from '../../skins/zones/ZonesBand';

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
  /** «band» — ряд белых полей на цветной полосе скина «Цветовые зоны». */
  variant?: 'card' | 'band';
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

  const developerOptions = (employeesQuery.data ?? [])
    .filter((e) => e.role && developerRoles.includes(e.role))
    .map((e) => ({
      value: e.jira_account_id,
      label: e.display_name,
    }));

  if (variant === 'band') {
    return (
      <div className="zn-band-row desk-band-filters">
        <BandField label="Команды">
          <Select
            mode="multiple"
            variant="borderless"
            allowClear
            placeholder="Выберите команды"
            style={{ minWidth: 120, maxWidth: 260 }}
            value={teams}
            onChange={onTeamsChange}
            loading={teamsQuery.isLoading}
            options={(teamsQuery.data ?? []).map((t) => ({ value: t, label: t }))}
            maxTagCount="responsive"
            popupMatchSelectWidth={false}
          />
        </BandField>
        <BandField label="Отдельные люди">
          <Select
            mode="multiple"
            variant="borderless"
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="Добрать разработчика"
            style={{ minWidth: 150, maxWidth: 220 }}
            value={developers}
            onChange={onDevelopersChange}
            loading={employeesQuery.isLoading}
            options={developerOptions}
            maxTagCount="responsive"
            popupMatchSelectWidth={false}
          />
        </BandField>
        <BandField label="Спринт">
          <Select
            mode="multiple"
            variant="borderless"
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="Все спринты"
            style={{ minWidth: 110, maxWidth: 200 }}
            value={sprints}
            onChange={onSprintsChange}
            options={sprintOptions.map((v) => ({ value: v, label: v }))}
            maxTagCount="responsive"
            popupMatchSelectWidth={false}
          />
        </BandField>
        <BandField label="Релиз">
          <Select
            mode="multiple"
            variant="borderless"
            allowClear
            showSearch
            optionFilterProp="label"
            placeholder="Все релизы"
            style={{ minWidth: 110, maxWidth: 200 }}
            value={releases}
            onChange={onReleasesChange}
            options={releaseOptions.map((v) => ({ value: v, label: v }))}
            maxTagCount="responsive"
            popupMatchSelectWidth={false}
          />
        </BandField>
        <Segmented
          value={mode}
          onChange={(v) => onModeChange(v as DeskMode)}
          options={[
            { value: 'open', label: 'Открытые сейчас' },
            { value: 'period', label: 'За период' },
            { value: 'all', label: 'Все задачи' },
          ]}
        />
        {mode === 'period' && (
          <BandField label="Период">
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
              style={{ width: 240 }}
            />
          </BandField>
        )}
        <label className="zn-band-switch">
          <Switch size="small" checked={showReviewed} onChange={onShowReviewedChange} />
          показывать просмотренные
        </label>
        <label
          className="zn-band-switch"
          title="Показывать закрытые подзадачи под их родителями — видно, разбита задача или нет"
        >
          <Switch
            size="small"
            checked={showDoneSubtasks}
            onChange={onShowDoneSubtasksChange}
            // В режиме «все задачи» закрытые подзадачи видны и без тумблера.
            disabled={mode === 'all'}
          />
          выполненные подзадачи
        </label>
        <Button icon={<SettingOutlined />} onClick={onToggleThresholds} title="Настройки вида" aria-label="Настройки вида" />
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
          options={developerOptions}
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
