import { Drawer, Spin, Tag, DatePicker, Typography, Space, App, Avatar } from 'antd';
import { UserOutlined } from '@ant-design/icons';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import dayjs from 'dayjs';
import { getEmployees, getEmployeeTeams, updateMembershipJoinedAt } from '../../api/employees';
import { DARK_THEME } from '../../utils/constants';

const { Text } = Typography;

interface Props {
  employeeId: string | null;
  onClose: () => void;
}

export default function EmployeeDrawer({ employeeId, onClose }: Props) {
  const { message } = App.useApp();
  const qc = useQueryClient();

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

  const mut = useMutation({
    mutationFn: ({ team, joined_at }: { team: string; joined_at: string | null }) =>
      updateMembershipJoinedAt(employeeId!, team, joined_at),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['employee', 'teams', employeeId] });
      qc.invalidateQueries({ queryKey: ['dashboard', 'hours-balance'] });
      message.success('Сохранено');
    },
    onError: () => message.error('Не удалось сохранить дату'),
  });

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
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
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
                {memberships.map((m) => (
                  <div
                    key={m.team}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '10px 14px',
                      marginBottom: 8,
                      background: DARK_THEME.darkAccent,
                      border: `1px solid ${DARK_THEME.border}`,
                      borderRadius: 6,
                      gap: 12,
                    }}
                  >
                    <Space size="small" style={{ flex: 1, minWidth: 0, overflow: 'hidden' }}>
                      <Text strong style={{ color: DARK_THEME.textPrimary }}>
                        {m.team}
                      </Text>
                      {m.is_primary && <Tag color="gold">основная</Tag>}
                    </Space>
                    <DatePicker
                      allowClear
                      size="small"
                      format="DD.MM.YYYY"
                      placeholder="В команде с…"
                      value={m.joined_at ? dayjs(m.joined_at) : null}
                      onChange={(date) =>
                        mut.mutate({
                          team: m.team,
                          joined_at: date ? date.format('YYYY-MM-DD') : null,
                        })
                      }
                    />
                  </div>
                ))}
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
              Если дата не указана — используется первая дата ворклога по задачам команды.
            </Text>
          </div>
        </Space>
      )}
    </Drawer>
  );
}
