import { Button, Card, Segmented, Select, Space, Switch, Typography } from 'antd';
import { SettingOutlined } from '@ant-design/icons';
import { useTeams } from '../../hooks/useSync';
import { useEmployees } from '../../hooks/useCapacity';

interface Props {
  teams: string[];
  onTeamsChange: (v: string[]) => void;
  developers: string[];
  onDevelopersChange: (v: string[]) => void;
  onlyOpen: boolean;
  onOnlyOpenChange: (v: boolean) => void;
  showReviewed: boolean;
  onShowReviewedChange: (v: boolean) => void;
  onToggleThresholds: () => void;
}

/** Шапка раздела: команды, добранные точечно люди, период, пороги. */
export function DeskFilters({
  teams, onTeamsChange,
  developers, onDevelopersChange,
  onlyOpen, onOnlyOpenChange,
  showReviewed, onShowReviewedChange,
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
          options={(employeesQuery.data ?? []).map((e) => ({
            value: e.jira_account_id,
            label: e.display_name,
          }))}
          maxTagCount="responsive"
        />

        <Segmented
          value={onlyOpen ? 'open' : 'all'}
          onChange={(v) => onOnlyOpenChange(v === 'open')}
          options={[
            { value: 'open', label: 'Открытые сейчас' },
            { value: 'all', label: 'Все задачи' },
          ]}
        />

        <Space size={6}>
          <Switch size="small" checked={showReviewed} onChange={onShowReviewedChange} />
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            показывать просмотренные
          </Typography.Text>
        </Space>

        <Button icon={<SettingOutlined />} onClick={onToggleThresholds} title="Пороги подсветки" />
      </Space>
    </Card>
  );
}
