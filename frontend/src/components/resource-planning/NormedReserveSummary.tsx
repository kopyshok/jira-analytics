import { useEffect, useState } from 'react';
import { App, Collapse, Select, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { OtherTeamWorkOut, ReserveOut, ReserveTypeRow } from '../../api/resourcePlanning';
import { useSetWorkTypeOverride } from '../../hooks/useResourcePlanning';
import { fmtHours, overuseLabel } from '../../utils/normedReserve';

interface Props {
  /** Запас нормированных работ команды плана на квартал. */
  reserve: ReserveOut;
}

const columns: ColumnsType<ReserveTypeRow> = [
  { title: 'Вид работ', dataIndex: 'label', key: 'label' },
  { title: 'Заложено', dataIndex: 'planned_hours', key: 'planned', align: 'right', render: fmtHours },
  { title: 'Заблокировано', dataIndex: 'blocked_hours', key: 'blocked', align: 'right', render: fmtHours },
  { title: 'Другие команды', dataIndex: 'other_teams_hours', key: 'other_teams', align: 'right', render: fmtHours },
  {
    title: 'Осталось',
    key: 'remaining',
    align: 'right',
    render: (_, row) =>
      row.overuse_hours > 0.5 ? (
        <span style={{ color: '#ff6b6b', fontWeight: 600 }}>
          −{fmtHours(row.overuse_hours)} <span style={{ fontWeight: 400 }}>(перерасход)</span>
        </span>
      ) : (
        fmtHours(row.remaining_hours)
      ),
  },
];

const overrideKey = (item: OtherTeamWorkOut) => `${item.backlog_item_id}::${item.team}`;

export default function NormedReserveSummary({ reserve }: Props) {
  const { message } = App.useApp();
  const setOverride = useSetWorkTypeOverride();
  const [pending, setPending] = useState<Set<string>>(new Set());
  // Выбор в селекте виден сразу, пока не подтянется пересчитанная диаграмма.
  const [localOverrides, setLocalOverrides] = useState<Record<string, string | null>>({});
  const overuseNote = overuseLabel(reserve);

  // Диаграмма перечиталась и уже отражает наш выбор — локальная подмена больше не нужна.
  useEffect(() => {
    setLocalOverrides((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const item of reserve.other_team_work) {
        const key = overrideKey(item);
        if (key in next) {
          const serverValue = item.is_manual ? item.work_type_id : null;
          if (serverValue === next[key]) {
            delete next[key];
            changed = true;
          }
        }
      }
      return changed ? next : prev;
    });
  }, [reserve.other_team_work]);

  const handleChange = async (item: OtherTeamWorkOut, value: string | undefined) => {
    const key = overrideKey(item);
    const nextValue = value ?? null;
    setLocalOverrides((prev) => ({ ...prev, [key]: nextValue }));
    setPending((prev) => new Set(prev).add(key));
    try {
      await setOverride.mutateAsync({ team: reserve.team, backlog_item_id: item.backlog_item_id, work_type_id: nextValue });
    } catch {
      message.error('Не удалось сохранить вид работ');
      setLocalOverrides((prev) => {
        const next = { ...prev };
        delete next[key];
        return next;
      });
    } finally {
      setPending((prev) => {
        const next = new Set(prev);
        next.delete(key);
        return next;
      });
    }
  };

  return (
    <div
      style={{
        background: '#0f2340',
        border: '1px solid #1e3a5f',
        borderRadius: 8,
        padding: 12,
        marginTop: 16,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <h3 style={{ fontSize: 13, fontWeight: 600, color: '#fff', margin: 0 }}>
            Нормированные работы — запас квартала
          </h3>
          {overuseNote && (
            <span style={{ fontSize: 11, fontWeight: 600, color: '#ff6b6b' }}>{overuseNote}</span>
          )}
        </div>
        <div style={{ fontSize: 11, color: 'var(--text-muted, #7a9ab8)' }}>{reserve.scenario_name}</div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 8 }}>
        {reserve.roles.map((r) => (
          <div key={r.role}>
            <div
              style={{
                fontSize: 10, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase',
                color: '#7a9ab8', marginBottom: 4,
              }}
            >
              {r.role_label}
            </div>
            <Table size="small" pagination={false} rowKey="work_type_id" columns={columns} dataSource={r.rows} />
          </div>
        ))}
      </div>

      {reserve.other_team_work.length > 0 && (
        <Collapse
          size="small"
          style={{ marginTop: 12 }}
          items={[
            {
              key: '1',
              label: `Работа наших людей в других командах (${reserve.other_team_work.length})`,
              children: (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {reserve.other_team_work.map((item) => {
                    const key = overrideKey(item);
                    const value =
                      key in localOverrides
                        ? localOverrides[key] ?? undefined
                        : item.is_manual ? item.work_type_id : undefined;
                    return (
                      <div
                        key={key}
                        style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: '#cfe1f5' }}
                      >
                        <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {item.issue_key ? `${item.issue_key} · ${item.title}` : item.title}
                        </span>
                        <span style={{ color: '#9ab3cc', flexShrink: 0 }}>{item.team}</span>
                        <span style={{ color: '#9ab3cc', flexShrink: 0, width: 56, textAlign: 'right' }}>
                          {fmtHours(item.hours)}
                        </span>
                        <Select
                          size="small"
                          allowClear
                          placeholder="Технические задачи"
                          aria-label={`Вид работ: ${item.issue_key ?? item.title}`}
                          options={reserve.work_types.map((w) => ({ label: w.label, value: w.id }))}
                          value={value}
                          disabled={pending.has(key)}
                          onChange={(v) => handleChange(item, v)}
                          style={{ width: 200, flexShrink: 0 }}
                        />
                      </div>
                    );
                  })}
                </div>
              ),
            },
          ]}
        />
      )}
    </div>
  );
}
