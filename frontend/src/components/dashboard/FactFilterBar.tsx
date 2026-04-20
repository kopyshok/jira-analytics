import { Checkbox, Select, Space, Typography } from 'antd';
import { useFactFilter, NO_TEAM_VALUE } from '../../hooks/useFactFilter';
import { useJiraTeams } from '../../hooks/useSync';

const { Text } = Typography;

export default function FactFilterBar() {
  const { selectedTeams, setSelectedTeams, matchEmployees, setMatchEmployees, matchIssues, setMatchIssues } = useFactFilter();
  const jiraTeams = useJiraTeams();
  const options = [
    ...((jiraTeams.data ?? []).map(t => ({ value: t, label: t }))),
    { value: NO_TEAM_VALUE, label: 'Без команды' },
  ];

  return (
    <Space wrap>
      <Select
        mode="multiple"
        allowClear
        placeholder="Команда"
        style={{ minWidth: 220 }}
        value={selectedTeams}
        onChange={setSelectedTeams}
        options={options}
        onDropdownVisibleChange={(open) => { if (open && !jiraTeams.data) jiraTeams.refetch(); }}
        loading={jiraTeams.isFetching}
        notFoundContent={jiraTeams.isError ? 'Настройте поля команды' : undefined}
        showSearch
        optionFilterProp="label"
      />
      <Checkbox
        checked={matchEmployees}
        onChange={(e) => setMatchEmployees(e.target.checked)}
      >
        <Text>Сотрудники</Text>
      </Checkbox>
      <Checkbox
        checked={matchIssues}
        onChange={(e) => setMatchIssues(e.target.checked)}
      >
        <Text>Задачи</Text>
      </Checkbox>
    </Space>
  );
}
