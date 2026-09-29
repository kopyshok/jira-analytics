import { useState } from 'react';
import { Drawer, Spin, Tag, DatePicker, Typography, Space, App, Avatar, Button, Switch, Popconfirm } from 'antd';
import { UserOutlined, SwapOutlined, DeleteOutlined } from '@ant-design/icons';
import { useQuery } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { getEmployees, getEmployeeTeams } from '../../api/employees';
import { getTeams } from '../../api/sync';
import {
  useUpdateMembershipJoinedAt,
  useUpdateMembershipLeftAt,
  useSetEmployeeActive,
} from '../../hooks/useCapacity';
import {
  useTeamRegistry,
  useSubgroupShares,
  useDeleteSubgroupShare,
} from '../../hooks/useTeamRegistry';
import { DARK_THEME } from '../../utils/constants';
import TransferTeamModal from './TransferTeamModal';
import SubgroupShareModal from './SubgroupShareModal';

const { Text } = Typography;

function MembershipGroups({ employeeId, team, subgroups, joinedAt }: {
  employeeId: string;
  team: string;
  subgroups: { id: string; name: string }[];
  /** Дата вступления в команду — для проверки, что история покрывает её начало. */
  joinedAt: string | null;
}) {
  const { message } = App.useApp();
  const { data: history = [] } = useSubgroupShares(employeeId, team);
  const del = useDeleteSubgroupShare();
  const [mode, setMode] = useState<'transfer' | 'split' | null>(null);
  const name = (id: string) => subgroups.find((g) => g.id === id)?.name ?? '—';

  // История начинается позже вступления в команду — первые дни без группы.
  const firstFrom = history[0]?.valid_from ?? null;
  const gapBeforeFirst = firstFrom && (!joinedAt || joinedAt < firstFrom);

  return (
    <div style={{ marginTop: 10 }}>
      <Text style={{ color: DARK_THEME.textSecondary, fontSize: 12 }}>Группы</Text>
      {history.length === 0 && (
        <div><Tag color="red">без группы — поправьте карточку</Tag></div>
      )}
      {gapBeforeFirst && (
        <div>
          <Tag color="red">без группы до {dayjs(firstFrom).format('DD.MM.YYYY')} — поправьте карточку</Tag>
        </div>
      )}
      {history.map((r) => (
        <div key={r.valid_from ?? 'base'} style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 12 }}>
          <span style={{ color: DARK_THEME.textMuted, minWidth: 110 }}>
            {r.valid_from ? `с ${dayjs(r.valid_from).format('DD.MM.YYYY')}` : 'с начала участия'}
          </span>
          <span style={{ color: DARK_THEME.textPrimary }}>
            {r.shares.map((s) => `${name(s.subgroup_id)}${s.percent < 100 ? ` ${s.percent}%` : ''}`).join(' · ')}
          </span>
          <Popconfirm
            title="Удалить запись?"
            description="Удаляйте только ошибочные записи — история перевода нужна для прошлых кварталов."
            onConfirm={() =>
              del.mutateAsync({ employeeId, team, valid_from: r.valid_from })
                .then(() => message.success('Запись удалена'))
                .catch(() => message.error('Не удалось удалить'))
            }
          >
            <Button size="small" type="text" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </div>
      ))}
      <Space size="small" style={{ marginTop: 6 }}>
        <Button size="small" onClick={() => setMode('transfer')}>Перевести в группу</Button>
        <Button size="small" onClick={() => setMode('split')}>Разделить между группами</Button>
      </Space>
      {mode && (
        <SubgroupShareModal
          key={mode}
          employeeId={employeeId} team={team} subgroups={subgroups}
          mode={mode}
          fromStartAllowed={!history.some((r) => r.valid_from === null)}
          firstRecord={history.length === 0}
          onClose={() => setMode(null)}
        />
      )}
    </div>
  );
}

interface Props {
  employeeId: string | null;
  onClose: () => void;
}

export default function EmployeeDrawer({ employeeId, onClose }: Props) {
  const { message } = App.useApp();
  const [transferFrom, setTransferFrom] = useState<string | null>(null);

  const { data: employees } = useQuery({
    queryKey: ['employees', false, null],
    queryFn: () => getEmployees(),
    staleTime: 30_000,
    enabled: !!employeeId,
  });
  const employee = employees?.find((e) => e.id === employeeId) ?? null;

  const { data: memberships = [], isLoading } = useQuery({
    queryKey: ['employee', 'teams', employeeId],
    queryFn: () => getEmployeeTeams(employeeId!),
    enabled: !!employeeId,
    staleTime: 30_000,
  });

  const { data: allTeams = [] } = useQuery({
    queryKey: ['teams'],
    queryFn: getTeams,
    staleTime: 60_000,
    enabled: !!employeeId,
  });

  const { data: teamRegistry = [] } = useTeamRegistry();

  const activeMut = useSetEmployeeActive();
  const joinedMut = useUpdateMembershipJoinedAt();
  const leftMut = useUpdateMembershipLeftAt();

  const saveDate = (
    mut: typeof joinedMut | typeof leftMut,
    vars: Record<string, unknown>,
  ) => {
    (mut.mutateAsync as (v: never) => Promise<unknown>)(vars as never)
      .then(() => message.success('Сохранено'))
      .catch(() => message.error('Дата не подходит: проверьте порядок и пересечения периодов'));
  };

  const initials = employee
    ? employee.display_name.split(' ').slice(0, 2).map((w) => w[0]).join('').toUpperCase()
    : '';

  const primaryTeam = memberships.find((m) => m.is_primary)?.team ?? null;

  return (
    <Drawer
      open={!!employeeId}
      onClose={onClose}
      size={480}
      title="Карточка сотрудника"
      destroyOnHidden
      styles={{
        body: { padding: 24 },
        header: {
          borderBottom: `1px solid ${DARK_THEME.border}`,
        },
      }}
    >
      {isLoading || !employee ? (
        <div style={{ textAlign: 'center', padding: 40 }}>
          <Spin />
        </div>
      ) : (
        <Space orientation="vertical" size="large" style={{ width: '100%' }}>
          {/* Header card */}
          <div
            style={{
              background: DARK_THEME.darkAccent,
              border: `1px solid ${DARK_THEME.border}`,
              borderRadius: 8,
              padding: '16px 20px',
              display: 'flex',
              alignItems: 'center',
              gap: 16,
            }}
          >
            {employee.avatar_url ? (
              <Avatar size={56} src={employee.avatar_url} />
            ) : (
              <Avatar
                size={56}
                icon={!initials ? <UserOutlined /> : undefined}
                style={{ background: '#1d3a66', fontSize: 20, fontWeight: 600 }}
              >
                {initials}
              </Avatar>
            )}
            <div>
              <div style={{ fontWeight: 600, fontSize: 16, color: DARK_THEME.textPrimary }}>
                {employee.display_name}
              </div>
              {employee.role && (
                <div style={{ color: DARK_THEME.textMuted, fontSize: 13, marginTop: 2 }}>
                  {employee.role}
                </div>
              )}
              {primaryTeam && (
                <div style={{ color: DARK_THEME.textHint, fontSize: 12, marginTop: 2 }}>
                  {primaryTeam}
                </div>
              )}
            </div>
            <Space size="small" style={{ marginInlineStart: 'auto' }}>
              <Text style={{ color: DARK_THEME.textSecondary, fontSize: 13 }}>Активен</Text>
              <Switch
                size="small"
                checked={employee.is_active}
                loading={activeMut.isPending}
                onChange={(checked) =>
                  activeMut
                    .mutateAsync({ employeeId: employee.id, is_active: checked })
                    .then(() =>
                      message.success(
                        checked
                          ? 'Сотрудник снова учитывается в расчётах'
                          : 'Сотрудник исключён из расчётов и виджетов',
                      ),
                    )
                    .catch(() => message.error('Не удалось сохранить'))
                }
              />
            </Space>
          </div>

          {/* Memberships section */}
          <div>
            <Text style={{ color: DARK_THEME.textSecondary, fontWeight: 600, fontSize: 14 }}>
              Членство в командах
            </Text>

            {memberships.length === 0 ? (
              <div style={{ color: DARK_THEME.textMuted, marginTop: 12 }}>
                Сотрудник не состоит ни в одной команде.
              </div>
            ) : (
              <div style={{ marginTop: 12 }}>
                {memberships.map((m) => {
                  const departed = !!m.left_at;
                  return (
                    <div
                      key={`${m.team}:${m.joined_at ?? ''}:${m.left_at ?? ''}`}
                      style={{
                        padding: '10px 14px',
                        marginBottom: 8,
                        background: DARK_THEME.darkAccent,
                        border: `1px solid ${DARK_THEME.border}`,
                        borderRadius: 6,
                        opacity: departed ? 0.6 : 1,
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          gap: 12,
                        }}
                      >
                        <Space size="small" style={{ flex: 1, minWidth: 0, overflow: 'hidden' }}>
                          <Text strong style={{ color: DARK_THEME.textPrimary }}>
                            {m.team}
                          </Text>
                          {m.is_primary && <Tag color="gold">основная</Tag>}
                          {departed && (
                            <Tag>выбыл {dayjs(m.left_at).format('DD.MM.YYYY')}</Tag>
                          )}
                        </Space>
                        {!departed && (
                          <Button
                            size="small"
                            type="text"
                            icon={<SwapOutlined />}
                            onClick={() => setTransferFrom(m.team)}
                          >
                            Перевести
                          </Button>
                        )}
                      </div>
                      <Space size="small" style={{ marginTop: 8 }}>
                        <DatePicker
                          allowClear
                          size="small"
                          format="DD.MM.YYYY"
                          placeholder="В команде с…"
                          value={m.joined_at ? dayjs(m.joined_at) : null}
                          onChange={(date) =>
                            saveDate(joinedMut, {
                              employeeId: employeeId!,
                              team: m.team,
                              joined_at: date ? date.format('YYYY-MM-DD') : null,
                            })
                          }
                        />
                        <DatePicker
                          allowClear
                          size="small"
                          format="DD.MM.YYYY"
                          placeholder="по…"
                          value={m.left_at ? dayjs(m.left_at) : null}
                          onChange={(date) =>
                            saveDate(leftMut, {
                              employeeId: employeeId!,
                              team: m.team,
                              left_at: date ? date.format('YYYY-MM-DD') : null,
                            })
                          }
                        />
                      </Space>
                      {teamRegistry.find((t) => t.name === m.team)?.has_subgroups && (
                        <MembershipGroups
                          employeeId={employeeId!}
                          team={m.team}
                          subgroups={teamRegistry.find((t) => t.name === m.team)!.subgroups}
                          joinedAt={m.joined_at ?? null}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
            )}

            <Text
              style={{
                display: 'block',
                marginTop: 12,
                fontSize: 12,
                color: DARK_THEME.textHint,
                fontStyle: 'italic',
              }}
            >
              Дата «по» — первый день вне команды. Если дата входа не указана —
              используется первая дата ворклога по задачам команды.
            </Text>
          </div>
        </Space>
      )}
      {transferFrom && employeeId && (
        <TransferTeamModal
          open
          employeeId={employeeId}
          fromTeam={transferFrom}
          availableTeams={allTeams}
          onClose={() => setTransferFrom(null)}
        />
      )}
    </Drawer>
  );
}
