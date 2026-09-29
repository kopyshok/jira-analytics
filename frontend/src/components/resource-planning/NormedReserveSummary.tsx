import { Fragment, useEffect, useRef, useState } from 'react';
import { App, Select } from 'antd';
import type { OtherTeamWorkOut, ReserveOut, ReserveTypeRow } from '../../api/resourcePlanning';
import { useSetWorkTypeOverride } from '../../hooks/useResourcePlanning';
import { useJiraBaseUrl } from '../../hooks/useSettings';
import { IssueKey } from '../teamdesk/IssueCells';
import {
  fmtHours,
  itemsForRow,
  overuseLabel,
  resolvedOverrideKeys,
  usageCaption,
  usagePct,
  usedHours,
  visibleReserveRows,
} from '../../utils/normedReserve';

interface Props {
  /** Запас нормированных работ команды плана на квартал. */
  reserve: ReserveOut;
}

/** Ключ строки таблицы запаса (React `key`) — уникален по задаче+команде+роли. */
const itemKey = (item: OtherTeamWorkOut) => `${item.backlog_item_id}::${item.team}::${item.role}`;

const thStyle: React.CSSProperties = {
  textAlign: 'left', fontSize: 11, fontWeight: 600, color: '#7a9ab8',
  padding: '4px', borderBottom: '1px solid #1e3a5f',
};
const tdStyle: React.CSSProperties = {
  fontSize: 12, color: '#cfe1f5', padding: '6px 4px', verticalAlign: 'top',
  borderBottom: '1px solid rgba(30,58,95,0.4)',
};

export default function NormedReserveSummary({ reserve }: Props) {
  const { message } = App.useApp();
  const setOverride = useSetWorkTypeOverride();
  const jiraBaseUrl = useJiraBaseUrl().data?.base_url ?? '';
  // Блок при каждом открытии плана свёрнут заново — состояние намеренно не персистится.
  const [expanded, setExpanded] = useState(false);
  // Раскрытые строки видов работ (задачи других команд) — ключ «роль::вид работ».
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());
  // Вид работ хранится на сервере per задача (backlog_item_id), а не per задача+роль — задача с
  // исполнителями двух ролей показана в двух строках, но подмена и блокировка селекта общие.
  const [pending, setPending] = useState<Set<string>>(new Set());
  // Выбор в селекте виден сразу, пока не подтянется пересчитанная диаграмма.
  const [localOverrides, setLocalOverrides] = useState<Record<string, string | null>>({});
  // Последний запрос на задачу — чтобы более ранний ответ не затёр состояние более нового.
  const requestSeqRef = useRef<Record<string, number>>({});
  const overuseNote = overuseLabel(reserve);
  const visibleRoles = visibleReserveRows(reserve);

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

  const toggleRow = (key: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const renderRowItems = (role: string, workTypeId: string) => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, padding: '6px 0' }}>
      {itemsForRow(reserve, role, workTypeId).map((item) => {
        const overrideKey = item.backlog_item_id;
        const value =
          overrideKey in localOverrides
            ? localOverrides[overrideKey] ?? undefined
            : item.is_manual ? item.work_type_id : undefined;
        return (
          <div key={itemKey(item)} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: '#cfe1f5' }}>
            <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {item.issue_key && (
                <>
                  <IssueKey issueKey={item.issue_key} jiraBaseUrl={jiraBaseUrl} style={{ fontSize: 'inherit', lineHeight: 'inherit' }} />
                  {' · '}
                </>
              )}
              {item.title}
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
      data-testid="rp-reserve-summary"
      style={{
        background: '#0f2340',
        border: '1px solid #1e3a5f',
        borderRadius: 8,
        padding: 12,
        marginTop: 16,
      }}
    >
      <button
        type="button"
        data-testid="rp-reserve-toggle"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%',
          background: 'transparent', border: 'none', padding: 0, margin: 0, cursor: 'pointer',
          font: 'inherit', color: 'inherit', textAlign: 'left',
        }}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span aria-hidden style={{ display: 'inline-block', width: 10, fontSize: 11, color: '#7a9ab8' }}>
            {expanded ? '▾' : '▸'}
          </span>
          <span style={{ fontSize: 13, fontWeight: 600, color: '#fff' }}>
            Нормированные работы — запас квартала
          </span>
        </span>
        {overuseNote ? (
          <span style={{ fontSize: 11, fontWeight: 600, color: '#ff6b6b' }}>⚠ {overuseNote}</span>
        ) : (
          <span style={{ fontSize: 11, color: '#7a9ab8' }}>перерасхода нет</span>
        )}
      </button>

      {expanded && (
        <div style={{ marginTop: 8 }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted, #7a9ab8)', marginBottom: 8 }}>
            {reserve.scenario_name}
          </div>

          {visibleRoles.length === 0 ? (
            <div style={{ fontSize: 12, color: '#7a9ab8' }}>
              Заблокированных периодов и работы в других командах нет — запас не расходуется
            </div>
          ) : (
            <table style={{ width: '100%', borderCollapse: 'collapse', tableLayout: 'fixed' }}>
              <colgroup>
                <col />
                <col style={{ width: 90 }} />
                <col style={{ width: 220 }} />
                <col style={{ width: 110 }} />
              </colgroup>
              <thead>
                <tr>
                  <th style={thStyle}>Вид работ</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>Заложено</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>Занято</th>
                  <th style={{ ...thStyle, textAlign: 'right' }}>Осталось</th>
                </tr>
              </thead>
              <tbody>
                {visibleRoles.map((r) => (
                  <Fragment key={r.role}>
                    <tr>
                      <td
                        colSpan={4}
                        style={{
                          fontSize: 10, fontWeight: 700, letterSpacing: '0.06em', textTransform: 'uppercase',
                          color: '#7a9ab8', padding: '8px 4px 4px',
                        }}
                      >
                        {r.role_label}
                      </td>
                    </tr>
                    {r.rows.map((row: ReserveTypeRow) => {
                      const rowKey = `${r.role}::${row.work_type_id}`;
                      const canExpand = row.other_teams_hours > 0;
                      const isOpen = expandedRows.has(rowKey);
                      const items = itemsForRow(reserve, r.role, row.work_type_id);
                      const used = usedHours(row);
                      const pct = usagePct(row);
                      const caption = usageCaption(row, items.length);
                      const isOveruse = row.overuse_hours > 0.5 || row.planned_hours <= 0;
                      return (
                        <Fragment key={rowKey}>
                          <tr>
                            <td style={tdStyle}>
                              {canExpand ? (
                                <span
                                  role="button"
                                  tabIndex={0}
                                  aria-expanded={isOpen}
                                  onClick={() => toggleRow(rowKey)}
                                  onKeyDown={(e) => {
                                    if (e.key === 'Enter' || e.key === ' ') {
                                      e.preventDefault();
                                      toggleRow(rowKey);
                                    }
                                  }}
                                  style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 4 }}
                                >
                                  <span aria-hidden style={{ display: 'inline-block', width: 10, fontSize: 10, color: '#7a9ab8' }}>
                                    {isOpen ? '▾' : '▸'}
                                  </span>
                                  {row.label}
                                </span>
                              ) : (
                                <span style={{ paddingLeft: 14 }}>{row.label}</span>
                              )}
                            </td>
                            <td style={{ ...tdStyle, textAlign: 'right' }}>{fmtHours(row.planned_hours)}</td>
                            <td style={tdStyle}>
                              <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <div style={{ flex: 1, height: 6, borderRadius: 3, background: 'rgba(255,255,255,0.08)', overflow: 'hidden' }}>
                                  <div style={{ width: `${pct}%`, height: '100%', background: isOveruse ? '#ff6b6b' : '#00c9c8' }} />
                                </div>
                                <span style={{ flexShrink: 0, textAlign: 'right', minWidth: 52 }}>{fmtHours(used)}</span>
                              </div>
                              {caption && (
                                <div style={{ fontSize: 10, color: '#7a9ab8', marginTop: 2 }}>{caption}</div>
                              )}
                            </td>
                            <td style={{ ...tdStyle, textAlign: 'right' }}>
                              {row.overuse_hours > 0.5 ? (
                                <span style={{ color: '#ff6b6b', fontWeight: 600 }}>
                                  −{fmtHours(row.overuse_hours)} <span style={{ fontWeight: 400, fontSize: 10 }}>перерасход</span>
                                </span>
                              ) : (
                                fmtHours(row.remaining_hours)
                              )}
                            </td>
                          </tr>
                          {canExpand && isOpen && (
                            <tr>
                              <td colSpan={4} style={{ padding: '0 4px 8px 18px', borderBottom: '1px solid rgba(30,58,95,0.4)' }}>
                                {renderRowItems(r.role, row.work_type_id)}
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      );
                    })}
                  </Fragment>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
