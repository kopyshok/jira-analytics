import { TeamOutlined, DownOutlined, SearchOutlined, CheckOutlined } from '@ant-design/icons';
import { Button, Checkbox, Empty, Input, Popover, Space, Tooltip, Typography } from 'antd';
import { useMemo, useState } from 'react';
import { useGlobalTeamFilter } from '../../hooks/useGlobalTeamFilter';
import { useTeams } from '../../hooks/useSync';

const { Text } = Typography;

export default function GlobalTeamFilterButton() {
  const { selectedTeams, setSelectedTeams, saving } = useGlobalTeamFilter();
  const { data: teams, isLoading } = useTeams();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<string[]>(selectedTeams);
  const [query, setQuery] = useState('');

  const label = selectedTeams.length === 0
    ? 'Все команды'
    : selectedTeams.length === 1
      ? selectedTeams[0]
      : `${selectedTeams[0]}, +${selectedTeams.length - 1}`;

  const noTeams = !isLoading && teams !== undefined && teams.length === 0;

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = teams ?? [];
    if (!q) return list;
    return list.filter((t) => t.toLowerCase().includes(q));
  }, [teams, query]);

  if (noTeams) {
    return (
      <Tooltip title="Загрузите команды в разделе Синхронизация">
        <Button icon={<TeamOutlined />} disabled>Команды</Button>
      </Tooltip>
    );
  }

  const toggle = (team: string) => {
    setDraft((prev) => (prev.includes(team) ? prev.filter((t) => t !== team) : [...prev, team]));
  };

  const allVisible = filtered.length > 0 && filtered.every((t) => draft.includes(t));
  const someVisible = filtered.some((t) => draft.includes(t));

  const toggleAllVisible = () => {
    if (allVisible) {
      setDraft((prev) => prev.filter((t) => !filtered.includes(t)));
    } else {
      setDraft((prev) => Array.from(new Set([...prev, ...filtered])));
    }
  };

  const apply = async () => {
    await setSelectedTeams(draft);
    setOpen(false);
  };

  const reset = () => setDraft([]);

  const content = (
    <div style={{ width: 320 }}>
      <Input
        allowClear
        prefix={<SearchOutlined style={{ opacity: 0.5 }} />}
        placeholder="Поиск команды"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        style={{ marginBottom: 8 }}
      />

      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '4px 4px 8px',
          borderBottom: '1px solid rgba(255,255,255,0.08)',
          marginBottom: 4,
        }}
      >
        <Checkbox
          checked={allVisible}
          indeterminate={!allVisible && someVisible}
          onChange={toggleAllVisible}
          disabled={filtered.length === 0}
        >
          <Text type="secondary" style={{ fontSize: 12 }}>
            {query ? 'Выбрать найденные' : 'Выбрать все'}
          </Text>
        </Checkbox>
        <Text type="secondary" style={{ fontSize: 12 }}>
          {draft.length} из {teams?.length ?? 0}
        </Text>
      </div>

      <div style={{ maxHeight: 280, overflowY: 'auto', margin: '0 -4px' }}>
        {filtered.length === 0 ? (
          <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Ничего не найдено" style={{ margin: '24px 0' }} />
        ) : (
          filtered.map((team) => {
            const checked = draft.includes(team);
            return (
              <div
                key={team}
                onClick={() => toggle(team)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '6px 8px',
                  borderRadius: 6,
                  cursor: 'pointer',
                  background: checked ? 'rgba(0,201,200,0.08)' : 'transparent',
                  transition: 'background 0.15s',
                }}
                onMouseEnter={(e) => {
                  if (!checked) e.currentTarget.style.background = 'rgba(255,255,255,0.04)';
                }}
                onMouseLeave={(e) => {
                  if (!checked) e.currentTarget.style.background = 'transparent';
                }}
              >
                <Checkbox checked={checked} onClick={(e) => e.stopPropagation()} onChange={() => toggle(team)} />
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {team}
                </span>
                {checked && <CheckOutlined style={{ color: '#00c9c8', fontSize: 12 }} />}
              </div>
            );
          })
        )}
      </div>

      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          paddingTop: 10,
          marginTop: 8,
          borderTop: '1px solid rgba(255,255,255,0.08)',
        }}
      >
        <Button type="link" size="small" onClick={reset} disabled={draft.length === 0} style={{ padding: 0 }}>
          Сбросить
        </Button>
        <Space>
          <Button size="small" onClick={() => { setDraft(selectedTeams); setOpen(false); }}>Отмена</Button>
          <Button size="small" type="primary" loading={saving} onClick={apply}>Применить</Button>
        </Space>
      </div>
    </div>
  );

  return (
    <Popover
      content={content}
      open={open}
      onOpenChange={(v) => {
        if (v) {
          setDraft(selectedTeams);
          setQuery('');
        }
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
