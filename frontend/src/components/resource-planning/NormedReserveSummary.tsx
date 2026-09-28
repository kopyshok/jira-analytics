import { useEffect, useRef, useState } from 'react';
import { App, Select, Table } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { OtherTeamWorkOut, ReserveOut, ReserveRoleOut, ReserveTypeRow } from '../../api/resourcePlanning';
import { useSetWorkTypeOverride } from '../../hooks/useResourcePlanning';
import { fmtHours, itemsForRow, overuseLabel, resolvedOverrideKeys } from '../../utils/normedReserve';

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

/** Ключ строки таблицы запаса (React `key`) — уникален по задаче+команде+роли. */
const itemKey = (item: OtherTeamWorkOut) => `${item.backlog_item_id}::${item.team}::${item.role}`;

export default function NormedReserveSummary({ reserve }: Props) {
  const { message } = App.useApp();
  const setOverride = useSetWorkTypeOverride();
  // Вид работ хранится на сервере per задача (backlog_item_id), а не per задача+роль — задача с
  // исполнителями двух ролей показана в двух таблицах, но подмена и блокировка селекта общие.
  const [pending, setPending] = useState<Set<string>>(new Set());
  // Выбор в селекте виден сразу, пока не подтянется пересчитанная диаграмма.
  const [localOverrides, setLocalOverrides] = useState<Record<string, string | null>>({});
  // Последний запрос на задачу — чтобы более ранний ответ не затёр состояние более нового.
  const requestSeqRef = useRef<Record<string, number>>({});
  const overuseNote = overuseLabel(reserve);

  // Диаграмма перечиталась и уже отражает наш выбор — локальная подмена больше не нужна.
  useEffect(() => {
    const resolved = resolvedOverrideKeys(reserve.other_team_work, localOverrides);
    if (resolved.length === 0) return;
    setLocalOverrides((prev) => {
      const next = { ...prev };
      for (const key of resolved) delete next[key];
      return next;
    });
  }, [reserve.other_team_work, localOverrides]);

  const handleChange = async (item: OtherTeamWorkOut, value: string | undefined) => {
    const key = item.backlog_item_id;
    const nextValue = value ?? null;
    const seq = (requestSeqRef.current[key] ?? 0) + 1;
    requestSeqRef.current[key] = seq;
    setLocalOverrides((prev) => ({ ...prev, [key]: nextValue }));
    setPending((prev) => new Set(prev).add(key));
    try {
      await setOverride.mutateAsync({ team: reserve.team, backlog_item_id: item.backlog_item_id, work_type_id: nextValue });
    } catch {
      message.error('Не удалось сохранить вид работ');
      // Более новый запрос по этой же задаче уже в работе — его состояние не трогаем.
      if (requestSeqRef.current[key] === seq) {
        setLocalOverrides((prev) => {
          const next = { ...prev };
          delete next[key];
          return next;
        });
      }
    } finally {
      if (requestSeqRef.current[key] === seq) {
        setPending((prev) => {
          const next = new Set(prev);
          next.delete(key);
          return next;
        });
      }
    }
  };

  const renderRowItems = (role: ReserveRoleOut, row: ReserveTypeRow) => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '4px 0' }}>
      {itemsForRow(reserve, role.role, row.work_type_id).map((item) => {
        const overrideKey = item.backlog_item_id;
        const value =
          overrideKey in localOverrides
            ? localOverrides[overrideKey] ?? undefined
            : item.is_manual ? item.work_type_id : undefined;
        return (
          <div key={itemKey(item)} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: '#cfe1f5' }}>
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
              disabled={pending.has(overrideKey)}
              onChange={(v) => handleChange(item, v)}
              style={{ width: 200, flexShrink: 0 }}
            />
          </div>
        );
      })}
    </div>
  );

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
            <Table
              size="small"
              pagination={false}
              rowKey="work_type_id"
              columns={columns}
              dataSource={r.rows}
              expandable={{
                rowExpandable: (row) => row.other_teams_hours > 0,
                expandedRowRender: (row) => renderRowItems(r, row),
              }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
