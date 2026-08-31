import { TeamOutlined, DownOutlined, SearchOutlined, CheckOutlined } from '@ant-design/icons';
import { Button, Checkbox, Empty, Input, Popover, Space, Tooltip, Typography } from 'antd';
import { useMemo, useState } from 'react';
import { useGlobalTeamFilter } from '../../hooks/useGlobalTeamFilter';
import { useTeams } from '../../hooks/useSync';
import { useTeamRegistry } from '../../hooks/useTeamRegistry';

const { Text } = Typography;

// Задачи и сотрудники, которых к группе не приписали. Без этого пункта сумма
// по группам не сходилась бы с командой, а неприписанный человек пропадал.
const NO_SUBGROUP = '__none__';

export default function GlobalTeamFilterButton() {
  const { selectedTeams, selectedSubgroups, setSelectedTeams, saving } = useGlobalTeamFilter();
  const { data: teams, isLoading } = useTeams();
  const { data: registry = [] } = useTeamRegistry();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<string[]>(selectedTeams);
  const [subgroupDraft, setSubgroupDraft] = useState<string[]>(selectedSubgroups);
  const [query, setQuery] = useState('');

  // Второй уровень появляется, только когда среди выбранных команд есть
  // делящаяся на группы. У остальных шапка не меняется вовсе.
  const splitTeams = useMemo(
    () => registry.filter((t) => t.has_subgroups && draft.includes(t.name)),
    [registry, draft],
  );

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
    setDraft((prev) => {
      const next = prev.includes(team) ? prev.filter((t) => t !== team) : [...prev, team];
      // Снятая команда уносит с собой свои группы, иначе фильтр остаётся
      // сужен группой, которой в выборке уже нет.
      const alive = new Set([
        NO_SUBGROUP,
        ...registry.filter((t) => next.includes(t.name)).flatMap((t) => t.subgroups.map((g) => g.id)),
      ]);
      setSubgroupDraft((sg) => sg.filter((id) => alive.has(id)));
      return next;
    });
  };

  const toggleSubgroup = (id: string) => {
    setSubgroupDraft((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
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
    await setSelectedTeams(draft, subgroupDraft);
    setOpen(false);
  };

  const reset = () => {
    setDraft([]);
    setSubgroupDraft([]);
  };

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

      {splitTeams.length > 0 && (
        <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid rgba(255,255,255,0.08)' }}>
          <Text type="secondary" style={{ fontSize: 12 }}>Группы</Text>
          <div style={{ maxHeight: 180, overflowY: 'auto', margin: '4px -4px 0' }}>
            {splitTeams.map((team) => (
              <div key={team.name}>
                <div style={{ padding: '4px 8px' }}>
                  <Text type="secondary" style={{ fontSize: 11 }}>{team.name}</Text>
                </div>
                {team.subgroups.map((g) => (
                  <div
                    key={g.id}
                    onClick={() => toggleSubgroup(g.id)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                      padding: '4px 8px 4px 20px',
                      borderRadius: 6,
                      cursor: 'pointer',
                    }}
                  >
                    <Checkbox
                      checked={subgroupDraft.includes(g.id)}
                      onClick={(e) => e.stopPropagation()}
                      onChange={() => toggleSubgroup(g.id)}
                    />
                    <span style={{ flex: 1 }}>{g.name}</span>
                  </div>
                ))}
                <div
                  onClick={() => toggleSubgroup(NO_SUBGROUP)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                    padding: '4px 8px 4px 20px',
                    borderRadius: 6,
                    cursor: 'pointer',
                  }}
                >
                  <Checkbox
                    checked={subgroupDraft.includes(NO_SUBGROUP)}
                    onClick={(e) => e.stopPropagation()}
                    onChange={() => toggleSubgroup(NO_SUBGROUP)}
                  />
                  <span style={{ flex: 1, opacity: 0.75 }}>Без группы</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

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
        <Button type="link" size="small" onClick={reset} disabled={draft.length === 0 && subgroupDraft.length === 0} style={{ padding: 0 }}>
          Сбросить
        </Button>
        <Space>
          <Button size="small" onClick={() => { setDraft(selectedTeams); setSubgroupDraft(selectedSubgroups); setOpen(false); }}>Отмена</Button>
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
          setSubgroupDraft(selectedSubgroups);
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
