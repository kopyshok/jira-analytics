import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import {
  App, Button, InputNumber, Popconfirm, Popover, Select, Space, Table, Tabs, Tag, Tooltip, Typography,
} from 'antd';
import {
  ArrowRightOutlined, DeleteOutlined, DisconnectOutlined, EditOutlined,
  InboxOutlined, LinkOutlined, PlusOutlined, ReloadOutlined, SettingOutlined, UndoOutlined,
} from '@ant-design/icons';
import backlogHelp from '../../../docs/help/backlog.md?raw';
import { useRegisterHelp } from '../contexts/HelpContext';
import PageHeader from '../components/shared/PageHeader';
import BacklogManualModal from '../components/backlog/BacklogManualModal';
import BacklogLinkJiraModal from '../components/backlog/BacklogLinkJiraModal';
import BacklogPlanningParamsModal from '../components/backlog/BacklogPlanningParamsModal';
import { statusTagColor } from '../utils/status';
import { daysSince, formatDateOnly } from '../utils/format';
import { DARK_THEME } from '../utils/constants';
import {
  useBacklogItems, useUpdateBacklogItem, useDeleteBacklogItem, useProjects,
  useUnlinkJira, useArchiveBacklogItem, useRestoreBacklogItem, useRefreshFromJira,
} from '../hooks/useBacklog';
import { useGlobalTeamFilter } from '../hooks/useGlobalTeamFilter';
import { useJiraSettings } from '../hooks/useSettings';
import { useEmployees } from '../hooks/useCapacity';
import { useRoles } from '../hooks/useRoles';
import { getRoleColor } from '../utils/roles';
import { OPO_COLOR } from '../utils/opo';
import BacklogRoleCell from '../components/planning/BacklogRoleCell';
import type {
  BacklogItemResponse, BacklogView,
} from '../types/api';

function groupByQuarterLabel(items: BacklogItemResponse[]): [string, BacklogItemResponse[]][] {
  const groups = new Map<string, BacklogItemResponse[]>();
  for (const item of items) {
    const key = item.quarter_label ?? '__none__';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(item);
  }
  return [...groups.entries()].sort(([a], [b]) => {
    if (a === '__none__') return 1;
    if (b === '__none__') return -1;
    return b.localeCompare(a); // newest quarter first
  });
}

export default function BacklogPage() {
  const { notification } = App.useApp();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const rawView = searchParams.get('view');
  const view: BacklogView =
    rawView === 'archived' ? 'archived' : rawView === 'active' ? 'active' : 'quarterly';

  const { queryParams } = useGlobalTeamFilter();
  const active = useBacklogItems('active', queryParams.teams);
  const archived = useBacklogItems('archived', queryParams.teams);
  const quarterly = useBacklogItems('quarterly', queryParams.teams);

  const { data: projects } = useProjects();
  const jiraSettings = useJiraSettings();
  const jiraBaseUrl = jiraSettings.data?.base_url ?? '';

  const update = useUpdateBacklogItem();
  const del = useDeleteBacklogItem();
  const unlink = useUnlinkJira();
  const archive = useArchiveBacklogItem();
  const restore = useRestoreBacklogItem();
  const refreshFromJiraMut = useRefreshFromJira();

  const [manualOpen, setManualOpen] = useState(false);
  const [editing, setEditing] = useState<BacklogItemResponse | null>(null);
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkTarget, setLinkTarget] = useState<BacklogItemResponse | null>(null);
  const [paramsOpen, setParamsOpen] = useState(false);
  const [paramsTarget, setParamsTarget] = useState<BacklogItemResponse | null>(null);
  useRegisterHelp('Бэклог инициатив', backlogHelp);

  const [groupByQuarter, setGroupByQuarter] = useState<boolean>(() => {
    return localStorage.getItem('backlog-archive-group') === 'true';
  });

  const toggleGroupByQuarter = (val: boolean) => {
    setGroupByQuarter(val);
    localStorage.setItem('backlog-archive-group', String(val));
  };

  const [groupActiveByQuarter, setGroupActiveByQuarter] = useState<boolean>(() => {
    return localStorage.getItem('backlog-active-group') === 'true';
  });

  const toggleGroupActiveByQuarter = (val: boolean) => {
    setGroupActiveByQuarter(val);
    localStorage.setItem('backlog-active-group', String(val));
  };

  const projectMap = useMemo(
    () => new Map(projects?.map((p) => [p.id, p]) ?? []),
    [projects],
  );

  const sortByPriority = (rows?: BacklogItemResponse[]) =>
    rows?.slice().sort((a, b) => (a.priority ?? 999) - (b.priority ?? 999));

  // BacklogChild с бэка — узкая схема. Маппим в shape BacklogItemResponse,
  // чтобы колонки таблицы (Идея с jira_key, Действия) рендерились так же,
  // как для родительских строк.
  const adaptChildren = (rows?: BacklogItemResponse[]): BacklogItemResponse[] | undefined =>
    rows?.map((r) => ({
      ...r,
      children: (r.children ?? []).map((c) => ({
        id: c.id,
        title: c.title,
        project_id: r.project_id,
        issue_id: c.issue_id,
        jira_key: c.key,
        jira_status: c.status ?? null,
        included_in_planning: c.included_in_planning,
        has_parent_in_backlog: true,
        has_children_in_backlog: false,
      })) as unknown as BacklogItemResponse['children'],
    }));

  const activeRows = useMemo(() => adaptChildren(sortByPriority(active.data)), [active.data]);
  const archivedRows = useMemo(() => adaptChildren(sortByPriority(archived.data)), [archived.data]);
  const quarterlyRows = useMemo(() => adaptChildren(sortByPriority(quarterly.data)), [quarterly.data]);

  const { data: employees = [] } = useEmployees();
  const { data: roles = [] } = useRoles();
  const activeEmployees = useMemo(
    () => employees.filter((e) => e.is_active),
    [employees],
  );

  const totalHoursAll = useMemo(
    () => (activeRows ?? []).reduce((sum, r) => {
      const an = r.estimate_analyst_hours ?? 0;
      const de = r.estimate_dev_hours ?? 0;
      const qa = r.estimate_qa_hours ?? 0;
      const op = r.estimate_opo_hours ?? 0;
      return sum + (r.estimate_hours ?? an + de + qa + op);
    }, 0),
    [activeRows],
  );

  const openCreate = () => { setEditing(null); setManualOpen(true); };
  const openEdit = (item: BacklogItemResponse) => { setEditing(item); setManualOpen(true); };
  const openLink = (item: BacklogItemResponse) => { setLinkTarget(item); setLinkOpen(true); };
  const openParams = (item: BacklogItemResponse) => { setParamsTarget(item); setParamsOpen(true); };

  const patch = (id: string, data: Parameters<typeof update.mutate>[0]['data']) => {
    update.mutate(
      { id, data },
      { onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }) },
    );
  };

  const handleRefreshFromJira = () => {
    refreshFromJiraMut.mutate(undefined, {
      onSuccess: () => notification.success({ title: 'Данные обновлены из Jira' }),
      onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }),
    });
  };

  const baseColumns = (editable: boolean) => [
    {
      title: 'Prio', dataIndex: 'priority', width: 110, fixed: 'left' as const,
      render: (v: number | null, r: BacklogItemResponse) =>
        editable ? (
          <InputNumber
            size="small"
            min={1}
            value={v ?? undefined}
            variant="borderless"
            style={{ width: 50 }}
            onBlur={(e) => {
              const raw = e.currentTarget.value.trim();
              const next = raw === '' ? null : Number(raw);
              if (next === v) return;
              patch(r.id, { priority: next as number });
            }}
          />
        ) : (
          <span style={{ color: 'var(--text-muted, #8faec8)' }}>{v ?? '—'}</span>
        ),
    },
    {
      title: 'Идея', dataIndex: 'title',
      render: (v: string, r: BacklogItemResponse) => (
        <Space orientation="vertical" size={0}>
          <Typography.Text strong>
            {r.has_parent_in_backlog && (
              <span style={{ color: 'var(--text-muted, #64748b)', marginRight: 6, fontFamily: 'monospace' }}>└─</span>
            )}
            {v}
          </Typography.Text>
          {r.jira_key && (
            jiraBaseUrl
              ? (
                <Typography.Link
                  href={`${jiraBaseUrl}/browse/${r.jira_key}`}
                  target="_blank"
                  rel="noreferrer"
                  style={{ fontSize: 12 }}
                >
                  {r.jira_key}
                </Typography.Link>
              )
              : <Typography.Text type="secondary" style={{ fontSize: 12 }}>{r.jira_key}</Typography.Text>
          )}
        </Space>
      ),
    },
    {
      title: 'Исполнитель',
      key: 'assignee',
      width: 140,
      render: (_: unknown, r: BacklogItemResponse) => {
        if (r.issue_id) {
          return <span style={{ fontSize: 12, color: 'var(--text-muted, #8faec8)' }}>{r.assignee_display_name ?? '—'}</span>;
        }
        return (
          <Select
            size="small"
            allowClear
            variant="borderless"
            value={r.assignee_employee_id ?? undefined}
            style={{ width: '100%', fontSize: 12 }}
            options={activeEmployees.map((e) => ({ label: e.display_name, value: e.id }))}
            onChange={(val) => patch(r.id, { assignee_employee_id: val ?? null })}
          />
        );
      },
    },
    {
      title: 'Заказчик',
      key: 'customer',
      width: 120,
      render: (_: unknown, r: BacklogItemResponse) => {
        if (r.issue_id) {
          return <span style={{ fontSize: 12, color: '#6b8fa8' }}>{r.customer ?? '—'}</span>;
        }
        return (
          <input
            style={{
              background: 'transparent',
              border: 'none',
              borderBottom: '1px dashed #1e3a5f',
              color: 'var(--text-muted, #8faec8)',
              fontSize: 12,
              padding: '2px 4px',
              width: '100%',
              outline: 'none',
            }}
            defaultValue={r.customer ?? ''}
            placeholder="Заказчик…"
            onBlur={(e) => {
              const next = e.target.value.trim() || null;
              if (next !== (r.customer ?? null)) {
                patch(r.id, { customer: next });
              }
            }}
          />
        );
      },
    },
    {
      title: 'Статус', dataIndex: 'jira_status', width: 150,
      sorter: (a: BacklogItemResponse, b: BacklogItemResponse) => {
        const ta = a.jira_status_changed_at ? new Date(a.jira_status_changed_at).getTime() : 0;
        const tb = b.jira_status_changed_at ? new Date(b.jira_status_changed_at).getTime() : 0;
        return ta - tb;
      },
      render: (_: unknown, r: BacklogItemResponse) => {
        if (!r.jira_status) return <span style={{ color: 'var(--text-muted, #8faec8)' }}>—</span>;
        const days = daysSince(r.jira_status_changed_at);
        let ageColor: string = DARK_THEME.textMuted;
        if (days !== null) {
          if (days >= 365) ageColor = '#ff7875';
          else if (days >= 180) ageColor = DARK_THEME.yellow;
        }
        return (
          <Space orientation="vertical" size={0} style={{ lineHeight: 1.1 }}>
            <Tag color={statusTagColor(r.jira_status, r.jira_status_category)} style={{ marginInlineEnd: 0 }}>
              {r.jira_status}
            </Tag>
            {r.jira_status_changed_at && (
              <Tooltip title={formatDateOnly(r.jira_status_changed_at)}>
                <span style={{ fontSize: 11, color: ageColor }}>
                  {days !== null ? `${days} д назад` : '—'}
                </span>
              </Tooltip>
            )}
          </Space>
        );
      },
    },
    {
      title: 'АН / ПР / ТС / ОПЭ',
      key: 'roles',
      width: 280,
      render: (_: unknown, r: BacklogItemResponse) => {
        const an = r.estimate_analyst_hours ?? 0;
        const de = r.estimate_dev_hours ?? 0;
        const qa = r.estimate_qa_hours ?? 0;
        const op = r.estimate_opo_hours ?? 0;
        const total = r.estimate_hours ?? an + de + qa + op;
        const isEditable = editable && !r.issue_id;

        const makeCell = (
          label: string,
          hours: number,
          field: 'estimate_analyst_hours' | 'estimate_dev_hours' | 'estimate_qa_hours' | 'estimate_opo_hours',
          color: string,
          involvement?: number | null,
          durationDays?: number | null,
        ) => {
          const cell = <BacklogRoleCell label={label} hours={hours} total={total} color={color} involvement={involvement} durationDays={durationDays} />;
          if (!isEditable) return cell;
          return (
            <Popover
              key={field}
              trigger="click"
              content={
                <InputNumber
                  autoFocus
                  min={0}
                  defaultValue={hours || undefined}
                  size="small"
                  style={{ width: 100 }}
                  onBlur={(e) => {
                    const raw = e.currentTarget.value.trim();
                    const next = raw === '' ? null : Number(raw);
                    if (next !== hours) {
                      patch(r.id, { [field]: next });
                    }
                  }}
                  onPressEnter={(e) => {
                    const raw = (e.target as HTMLInputElement).value.trim();
                    const next = raw === '' ? null : Number(raw);
                    if (next !== hours) {
                      patch(r.id, { [field]: next });
                    }
                  }}
                />
              }
            >
              <span style={{ cursor: 'pointer' }}>{cell}</span>
            </Popover>
          );
        };

        return (
          <div style={{ display: 'flex', gap: 4 }}>
            {makeCell('АН', an, 'estimate_analyst_hours', getRoleColor(roles, 'analyst'), r.involvement_analyst, r.duration_analyst_days)}
            {makeCell('ПР', de, 'estimate_dev_hours', getRoleColor(roles, 'dev'), r.involvement_dev, r.duration_dev_days)}
            {makeCell('ТС', qa, 'estimate_qa_hours', getRoleColor(roles, 'qa'), r.involvement_qa, r.duration_qa_days)}
            {makeCell('ОПЭ', op, 'estimate_opo_hours', OPO_COLOR, r.involvement_launch, r.duration_launch_days)}
          </div>
        );
      },
    },
    {
      title: 'ОПЭ→АН', dataIndex: 'opo_analyst_ratio', width: 90,
      render: (v: number | null, r: BacklogItemResponse) => {
        if (!editable) {
          return <span style={{ color: 'var(--text-muted, #8faec8)' }}>{v ?? '—'}</span>;
        }
        return (
          <Tooltip title="Какая часть часов ОПЭ идёт на аналитика (остальное — на ПР)">
            <InputNumber
              size="small"
              min={0}
              max={1}
              step={0.05}
              value={v ?? 0.5}
              variant="borderless"
              style={{ width: 75 }}
              onBlur={(e) => {
                const raw = e.currentTarget.value.trim();
                const next = raw === '' ? null : Number(raw);
                if (next === v) return;
                patch(r.id, { opo_analyst_ratio: next as number });
              }}
            />
          </Tooltip>
        );
      },
    },
    {
      title: 'Всего часов',
      key: 'total_hours',
      width: 90,
      align: 'right' as const,
      render: (_: unknown, r: BacklogItemResponse) => {
        const an = r.estimate_analyst_hours ?? 0;
        const de = r.estimate_dev_hours ?? 0;
        const qa = r.estimate_qa_hours ?? 0;
        const op = r.estimate_opo_hours ?? 0;
        const total = r.estimate_hours ?? an + de + qa + op;
        const pct = totalHoursAll > 0 ? Math.round((total / totalHoursAll) * 100) : 0;
        return (
          <div style={{ textAlign: 'right' }}>
            <span style={{ fontFamily: 'monospace', fontSize: 14, fontWeight: 700, color: '#e8f4f8' }}>
              {Math.round(total)} ч
            </span>
            {totalHoursAll > 0 && (
              <div style={{ fontSize: 10, color: 'var(--text-muted, #4a6a80)', marginTop: 1 }}>
                {pct}% ресурса
              </div>
            )}
          </div>
        );
      },
    },
    {
      title: 'Проект', dataIndex: 'project_id', width: 110,
      render: (id: string | null) => {
        if (!id) return <span>—</span>;
        const p = projectMap.get(id);
        return p ? <Tooltip title={p.name}><span>{p.key}</span></Tooltip> : id;
      },
    },
  ];

  const actionsActive = (r: BacklogItemResponse) => (
    <Space size={4}>
      {r.jira_key && (
        <Tooltip title="Открыть страницу проекта">
          <Button
            icon={<ArrowRightOutlined />}
            size="small"
            onClick={() => navigate(`/projects/${encodeURIComponent(r.jira_key!)}`)}
          />
        </Tooltip>
      )}
      {r.issue_id ? (
        <Popconfirm
          title="Отвязать от Jira?"
          description="Идея останется в бэклоге, но потеряет связь с задачей."
          onConfirm={() => unlink.mutate(r.id, {
            onSuccess: () => notification.success({ title: 'Отвязано' }),
            onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }),
          })}
        >
          <Tooltip title="Отвязать от Jira">
            <Button icon={<DisconnectOutlined />} size="small" />
          </Tooltip>
        </Popconfirm>
      ) : (
        <>
          <Tooltip title="Связать с Jira">
            <Button icon={<LinkOutlined />} size="small" onClick={() => openLink(r)} />
          </Tooltip>
          <Tooltip title="Редактировать">
            <Button icon={<EditOutlined />} size="small" onClick={() => openEdit(r)} />
          </Tooltip>
        </>
      )}
      <Tooltip title="Параметры планирования">
        <Button icon={<SettingOutlined />} size="small" onClick={() => openParams(r)} />
      </Tooltip>
      <Popconfirm
        title="Убрать из активного бэклога?"
        description="Инициатива попадёт в раздел «Архив». Связь с Jira сохраняется."
        onConfirm={() => archive.mutate(r.id, {
          onSuccess: () => notification.success({ title: 'Архивировано' }),
          onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }),
        })}
      >
        <Tooltip title="Архивировать">
          <Button icon={<InboxOutlined />} size="small" />
        </Tooltip>
      </Popconfirm>
      <Popconfirm
        title="Удалить идею?"
        description="Элемент будет убран из всех черновиков сценариев."
        onConfirm={() => del.mutate(r.id, {
          onSuccess: (res) => {
            if (res.affected_scenarios.length > 0) {
              notification.success({
                title: 'Удалено',
                description:
                  `Убрано из ${res.affected_scenarios.length} сценариев: ` +
                  res.affected_scenarios.map((s) => s.name).join(', '),
              });
            }
          },
          onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }),
        })}
      >
        <Button icon={<DeleteOutlined />} size="small" danger />
      </Popconfirm>
    </Space>
  );

  const actionsArchived = (r: BacklogItemResponse) => (
    <Space size={4}>
      <Popconfirm
        title="Вернуть в активный бэклог?"
        onConfirm={() => restore.mutate(r.id, {
          onSuccess: () => notification.success({ title: 'Восстановлено' }),
          onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }),
        })}
      >
        <Tooltip title="Восстановить">
          <Button icon={<UndoOutlined />} size="small" />
        </Tooltip>
      </Popconfirm>
      {!r.issue_id && (
        <Tooltip title="Редактировать">
          <Button icon={<EditOutlined />} size="small" onClick={() => openEdit(r)} />
        </Tooltip>
      )}
      <Tooltip title="Параметры планирования">
        <Button icon={<SettingOutlined />} size="small" onClick={() => openParams(r)} />
      </Tooltip>
      <Popconfirm
        title="Удалить идею?"
        onConfirm={() => del.mutate(r.id, {
          onSuccess: () => notification.success({ title: 'Удалено' }),
          onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }),
        })}
      >
        <Button icon={<DeleteOutlined />} size="small" danger />
      </Popconfirm>
    </Space>
  );

  const quarterlyColumns = [
    ...baseColumns(false).filter((c) => !('dataIndex' in c && c.dataIndex === 'project_id')),
    {
      title: 'Цели',
      dataIndex: 'goals',
      key: 'goals',
      width: 140,
      sorter: (a: BacklogItemResponse, b: BacklogItemResponse) =>
        (a.goals ?? '').localeCompare(b.goals ?? ''),
      render: (v: string | null) => {
        if (!v) return <span style={{ color: 'var(--text-muted, #4a6a80)' }}>—</span>;
        return (
          <Space size={4} wrap>
            {v.split(',').map((s) => s.trim()).filter(Boolean).map((tag) => (
              <Tag key={tag} color="purple" style={{ marginInlineEnd: 0 }}>{tag}</Tag>
            ))}
          </Space>
        );
      },
    },
    {
      title: 'Сценарий',
      key: 'scenario',
      width: 180,
      render: (_: unknown, r: BacklogItemResponse) => {
        if (!r.approved_scenarios?.length)
          return <span style={{ color: 'var(--text-muted, #8faec8)' }}>—</span>;
        return (
          <Space orientation="vertical" size={2}>
            {r.approved_scenarios.map((s) => (
              <Tag key={s.id} color="cyan" style={{ marginInlineEnd: 0 }}>
                {s.name}
              </Tag>
            ))}
          </Space>
        );
      },
    },
    {
      title: 'Действия',
      key: 'actions',
      width: 80,
      fixed: 'right' as const,
      render: (_: unknown, r: BacklogItemResponse) => (
        <Tooltip title="Параметры планирования">
          <Button icon={<SettingOutlined />} size="small" onClick={() => openParams(r)} />
        </Tooltip>
      ),
    },
  ];

  // Раскрытие дерева RFA → дочки. defaultExpandAllRows срабатывает только
  // на mount; данные приходят async, поэтому удерживаем expandedRowKeys
  // через useEffect — авто-раскрытие всех родителей при изменении data.
  const [expandedKeys, setExpandedKeys] = useState<React.Key[]>([]);
  useEffect(() => {
    const collect = (rows?: BacklogItemResponse[]) =>
      (rows ?? [])
        .filter((r) => Array.isArray(r.children) && r.children.length > 0)
        .map((r) => r.id);
    setExpandedKeys((prev) => {
      const next = new Set<React.Key>(prev);
      collect(activeRows).forEach((k) => next.add(k));
      collect(quarterlyRows).forEach((k) => next.add(k));
      collect(archivedRows).forEach((k) => next.add(k));
      return Array.from(next);
    });
  }, [activeRows, quarterlyRows, archivedRows]);

  const nestedExpandable = {
    expandedRowKeys: expandedKeys,
    onExpandedRowsChange: (keys: readonly React.Key[]) => setExpandedKeys([...keys]),
    columnWidth: 36,
    fixed: 'left' as const,
  };

  const quarterlyTable = (
    <div>
      <Button
        size="small"
        type={groupActiveByQuarter ? 'primary' : 'default'}
        ghost={groupActiveByQuarter}
        onClick={() => toggleGroupActiveByQuarter(!groupActiveByQuarter)}
        style={{ marginBottom: 8 }}
      >
        {groupActiveByQuarter ? 'Сгруппировано по кварталам' : 'Группировать по кварталам'}
      </Button>
      {groupActiveByQuarter ? (
        (() => {
          const groups = groupByQuarterLabel(quarterlyRows ?? []);
          if (groups.length === 0) {
            return (
              <Table<BacklogItemResponse>
                dataSource={[]}
                columns={quarterlyColumns}
                rowKey="id"
                loading={quarterly.isLoading}
                size="small"
                pagination={false}
                scroll={{ x: true }}
              />
            );
          }
          return (
            <Tabs
              size="small"
              items={groups.map(([key, rows]) => ({
                key,
                label: (
                  <Space size={6}>
                    {key === '__none__'
                      ? <span style={{ color: 'var(--text-muted, #4a6a80)' }}>Без квартала</span>
                      : <Tag color="purple" style={{ marginInlineEnd: 0 }}>{key}</Tag>
                    }
                    <span style={{ fontSize: 12, color: 'var(--text-muted, #4a6a80)' }}>{rows.length}</span>
                  </Space>
                ),
                children: (
                  <Table<BacklogItemResponse>
                    dataSource={rows}
                    columns={quarterlyColumns}
                    rowKey="id"
                    loading={quarterly.isLoading}
                    size="small"
                    pagination={false}
                    scroll={{ x: true }}
                    expandable={nestedExpandable}
                  />
                ),
              }))}
            />
          );
        })()
      ) : (
        <Table<BacklogItemResponse>
          dataSource={quarterlyRows}
          rowKey="id"
          loading={quarterly.isLoading}
          pagination={false}
          size="small"
          scroll={{ x: 1400 }}
          columns={quarterlyColumns}
          expandable={nestedExpandable}
        />
      )}
    </div>
  );

  const activeTable = (
    <Table<BacklogItemResponse>
      dataSource={activeRows}
      rowKey="id"
      loading={active.isLoading}
      pagination={false}
      size="small"
      scroll={{ x: 1400 }}
      columns={[
        ...baseColumns(true),
        { title: 'Действия', width: 210, fixed: 'right' as const, render: (_, r) => actionsActive(r) },
      ]}
      expandable={nestedExpandable}
    />
  );

  const archiveColumns = [
    ...baseColumns(false),
    {
      title: 'Квартал',
      key: 'quarter_label',
      width: 110,
      sorter: (a: BacklogItemResponse, b: BacklogItemResponse) => {
        if (!a.quarter_label && !b.quarter_label) return 0;
        if (!a.quarter_label) return 1;
        if (!b.quarter_label) return -1;
        return a.quarter_label.localeCompare(b.quarter_label);
      },
      defaultSortOrder: 'descend' as const,
      render: (_: unknown, r: BacklogItemResponse) =>
        r.quarter_label
          ? <Tag color="purple" style={{ marginInlineEnd: 0 }}>{r.quarter_label}</Tag>
          : <span style={{ color: 'var(--text-muted, #4a6a80)' }}>—</span>,
    },
    { title: 'Действия', width: 160, fixed: 'right' as const, render: (_: unknown, r: BacklogItemResponse) => actionsArchived(r) },
  ];

  const archivedTable = (
    <div>
      <Button
        size="small"
        type={groupByQuarter ? 'primary' : 'default'}
        ghost={groupByQuarter}
        onClick={() => toggleGroupByQuarter(!groupByQuarter)}
        style={{ marginBottom: 8 }}
      >
        {groupByQuarter ? 'Сгруппировано по кварталам' : 'Группировать по кварталам'}
      </Button>
      {groupByQuarter ? (
        groupByQuarterLabel(archivedRows ?? []).map(([key, rows]) => (
          <div key={key} style={{ marginBottom: 16 }}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8,
              padding: '6px 0', borderBottom: '1px solid rgba(255,255,255,0.06)',
            }}>
              {key === '__none__'
                ? <span style={{ color: 'var(--text-muted, #4a6a80)', fontWeight: 600 }}>Без квартала</span>
                : <Tag color="purple">{key}</Tag>
              }
              <span style={{ fontSize: 12, color: 'var(--text-muted, #4a6a80)' }}>{rows.length} {rows.length === 1 ? 'задача' : 'задач'}</span>
            </div>
            <Table<BacklogItemResponse>
              dataSource={rows}
              columns={archiveColumns}
              rowKey="id"
              loading={archived.isLoading}
              size="small"
              pagination={false}
              scroll={{ x: true }}
              expandable={nestedExpandable}
            />
          </div>
        ))
      ) : (
        <Table<BacklogItemResponse>
          dataSource={archivedRows}
          rowKey="id"
          loading={archived.isLoading}
          pagination={{ pageSize: 50 }}
          size="small"
          scroll={{ x: 1400 }}
          columns={archiveColumns}
          expandable={nestedExpandable}
        />
      )}
    </div>
  );

  return (
    <Space orientation="vertical" size="large" style={{ width: '100%' }}>
      <PageHeader
        eyebrow="Планирование"
        title="Целевые задачи"
        subtitle='Активные задачи текущего квартала и бэклог инициатив'
        actions={
          <Space>
            <Button
              icon={<ReloadOutlined />}
              onClick={handleRefreshFromJira}
              loading={refreshFromJiraMut.isPending}
            >
              Обновить с Jira
            </Button>
            <Button icon={<PlusOutlined />} type="primary" onClick={openCreate}>
              Идея вручную
            </Button>
          </Space>
        }
      />


      <BacklogManualModal
        open={manualOpen}
        item={editing}
        onClose={() => { setManualOpen(false); setEditing(null); }}
      />
      <BacklogLinkJiraModal
        open={linkOpen}
        item={linkTarget}
        onClose={() => { setLinkOpen(false); setLinkTarget(null); }}
      />
      <BacklogPlanningParamsModal
        open={paramsOpen}
        item={paramsTarget}
        onClose={() => { setParamsOpen(false); setParamsTarget(null); }}
      />

      <Tabs
        activeKey={view}
        onChange={(k) => {
          const next = new URLSearchParams(searchParams);
          next.set('view', k);
          setSearchParams(next, { replace: true });
        }}
        items={[
          {
            key: 'quarterly',
            label: `Активные (${quarterlyRows?.length ?? 0})`,
            children: quarterlyTable,
          },
          {
            key: 'active',
            label: `Бэклог (${activeRows?.length ?? 0})`,
            children: activeTable,
          },
          {
            key: 'archived',
            label: `Архив (${archivedRows?.length ?? 0})`,
            children: archivedTable,
          },
        ]}
      />
    </Space>
  );
}
