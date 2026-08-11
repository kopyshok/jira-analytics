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
  /** Статусы, встретившиеся в срезе, в порядке групп. */
  statusOptions: string[];
  statusCounters: string[];
  onStatusCountersChange: (v: string[]) => void;
  onToggleThresholds: () => void;
}

/** Шапка раздела: команды, добранные точечно люди, период, пороги. */
export function DeskFilters({
  teams, onTeamsChange,
  developers, onDevelopersChange, developerRoles,
  mode, onModeChange,
  periodStart, periodEnd, onPeriodChange,
  showReviewed, onShowReviewedChange,
  showDoneSubtasks, onShowDoneSubtasksChange,
  statusOptions, statusCounters, onStatusCountersChange,
  onToggleThresholds,
}: Props) {
  const teamsQuery = useTeams();
  const employeesQuery = useEmployees({ isActive: true });

  return (
    <Card size="small" styles={{ body: { padding: '10px 12px' } }}>
      <Space wrap size={[10, 8]} style={{ width: '100%' }}>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>КОМАНДЫ</Typography.Text>
        <Select
          mode="multiple"
          allowClear
          placeholder="Выберите команды"
          style={{ minWidth: 340 }}
          value={teams}
          onChange={onTeamsChange}
          loading={teamsQuery.isLoading}
          options={(teamsQuery.data ?? []).map((t) => ({ value: t, label: t }))}
          maxTagCount="responsive"
        />

        <Typography.Text type="secondary" style={{ fontSize: 12 }}>ОТДЕЛЬНЫЕ ЛЮДИ</Typography.Text>
        <Select
          mode="multiple"
          allowClear
          showSearch
          optionFilterProp="label"
          placeholder="Добрать разработчика"
          style={{ minWidth: 260 }}
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
          <DatePicker.RangePicker
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

        <Space size={6}>
          <Switch size="small" checked={showReviewed} onChange={onShowReviewedChange} />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            показывать просмотренные
          </Typography.Text>
        </Space>

        <Space size={6}>
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

        <Typography.Text type="secondary" style={{ fontSize: 12 }}>СЧЁТЧИКИ СТАТУСОВ</Typography.Text>
        <Select
          mode="multiple"
          allowClear
          // Пусто = все статусы среза: польза сразу, настраивать не обязательно.
          placeholder="все статусы"
          style={{ minWidth: 260 }}
          value={statusCounters}
          onChange={onStatusCountersChange}
          options={statusOptions.map((s) => ({ value: s, label: s }))}
          maxTagCount="responsive"
        />

        <Button icon={<SettingOutlined />} onClick={onToggleThresholds} title="Пороги подсветки" />
      </Space>
    </Card>
  );
}
