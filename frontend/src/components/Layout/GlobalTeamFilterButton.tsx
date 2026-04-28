import { TeamOutlined, DownOutlined } from '@ant-design/icons';
import { Button, Popover, Select, Space, Tooltip } from 'antd';
import { useState } from 'react';
import { useGlobalTeamFilter } from '../../hooks/useGlobalTeamFilter';
import { useTeams } from '../../hooks/useSync';

export default function GlobalTeamFilterButton() {
  const { selectedTeams, setSelectedTeams, saving } = useGlobalTeamFilter();
  const { data: teams, isLoading } = useTeams();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<string[]>(selectedTeams);

  const label = selectedTeams.length === 0
    ? 'Все команды'
    : selectedTeams.length === 1
      ? selectedTeams[0]
      : `${selectedTeams[0]}, +${selectedTeams.length - 1}`;

  const noTeams = !isLoading && teams !== undefined && teams.length === 0;

  if (noTeams) {
    return (
      <Tooltip title="Загрузите команды в разделе Синхронизация">
        <Button icon={<TeamOutlined />} disabled>Команды</Button>
      </Tooltip>
    );
  }

  const content = (
    <div style={{ width: 320 }}>
      <Select
        mode="multiple"
        value={draft}
        onChange={setDraft}
        options={(teams ?? []).map((t) => ({ value: t, label: t }))}
        placeholder="Все команды"
        style={{ width: '100%' }}
        showSearch
        allowClear
        loading={isLoading}
        maxTagCount="responsive"
      />
      <Space style={{ marginTop: 12, width: '100%', justifyContent: 'flex-end' }}>
        <Button onClick={() => { setDraft(selectedTeams); setOpen(false); }}>Отмена</Button>
        <Button
          type="primary"
          loading={saving}
          onClick={async () => {
            await setSelectedTeams(draft);
            setOpen(false);
          }}
        >
          Применить
        </Button>
      </Space>
    </div>
  );

  return (
    <Popover
      content={content}
      open={open}
      onOpenChange={(v) => {
        if (v) setDraft(selectedTeams);
        setOpen(v);
      }}
      trigger="click"
      placement="bottomRight"
    >
      <Button icon={<TeamOutlined />} loading={isLoading || saving}>
        <Space size={4}>
          {label}
          <DownOutlined style={{ fontSize: 10 }} />
        </Space>
      </Button>
    </Popover>
  );
}
