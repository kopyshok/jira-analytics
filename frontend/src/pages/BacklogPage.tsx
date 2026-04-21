import { useCallback, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router';
import {
  App, Button, InputNumber, Popconfirm, Select, Space, Table, Tabs, Tag, Tooltip, Typography,
} from 'antd';
import {
  DeleteOutlined, DisconnectOutlined, EditOutlined, HolderOutlined,
  InboxOutlined, LinkOutlined, PlusOutlined, ReloadOutlined, UndoOutlined,
} from '@ant-design/icons';
import { DndContext, closestCenter, type DragEndEvent } from '@dnd-kit/core';
import { SortableContext, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { restrictToVerticalAxis } from '@dnd-kit/modifiers';
import PageHeader from '../components/shared/PageHeader';
import BacklogManualModal from '../components/backlog/BacklogManualModal';
import BacklogLinkJiraModal from '../components/backlog/BacklogLinkJiraModal';
import { statusTagColor } from '../utils/status';
import { daysSince, formatDateOnly } from '../utils/format';
import { DARK_THEME } from '../utils/constants';
import {
  useBacklogItems, useUpdateBacklogItem, useDeleteBacklogItem, useProjects,
  useUnlinkJira, useRefreshFromJira, useArchiveBacklogItem, useRestoreBacklogItem,
} from '../hooks/useBacklog';
import { useJiraSettings } from '../hooks/useSettings';
import { useEmployees } from '../hooks/useCapacity';
import type {
  BacklogItemResponse, BacklogImpactRisk, BacklogView,
} from '../types/api';

const IMPACT_RISK_OPTIONS: { value: BacklogImpactRisk; label: string }[] = [
  { value: 'low',    label: 'Низкий' },
  { value: 'medium', label: 'Средний' },
  { value: 'high',   label: 'Высокий' },
];

const IMPACT_RISK_COLOR: Record<BacklogImpactRisk, string> = {
  low: 'default',
  medium: 'gold',
  high: 'red',
};

const IMPACT_RISK_LABEL: Record<BacklogImpactRisk, string> = {
  low: 'Низкий',
  medium: 'Средний',
  high: 'Высокий',
};

function DragHandle({ id }: { id: string }) {
  const { attributes, listeners } = useSortable({ id });
  return (
    <HolderOutlined
      style={{ cursor: 'grab', color: '#8faec8' }}
      {...attributes}
      {...listeners}
    />
  );
}

function SortableRow(props: React.HTMLAttributes<HTMLTableRowElement> & { 'data-row-key'?: string }) {
  const id = props['data-row-key'] ?? '';
  const { setNodeRef, transform, transition, isDragging } = useSortable({ id });
  return (
    <tr
      {...props}
      ref={setNodeRef}
      style={{
        ...props.style,
        transform: CSS.Translate.toString(transform),
        transition,
        opacity: isDragging ? 0.5 : 1,
      }}
    />
  );
}

export default function BacklogPage() {
  const { notification } = App.useApp();
  const [searchParams, setSearchParams] = useSearchParams();
  const rawView = searchParams.get('view');
  const view: BacklogView =
    rawView === 'archived' ? rawView : 'active';

  const active = useBacklogItems('active');
  const archived = useBacklogItems('archived');

  const { data: projects } = useProjects();
  const jiraSettings = useJiraSettings();
  const jiraBaseUrl = jiraSettings.data?.base_url ?? '';

  const update = useUpdateBacklogItem();
  const del = useDeleteBacklogItem();
  const unlink = useUnlinkJira();
  const refreshFromJira = useRefreshFromJira();
  const archive = useArchiveBacklogItem();
  const restore = useRestoreBacklogItem();

  const [manualOpen, setManualOpen] = useState(false);
  const [editing, setEditing] = useState<BacklogItemResponse | null>(null);
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkTarget, setLinkTarget] = useState<BacklogItemResponse | null>(null);

  const projectMap = useMemo(
    () => new Map(projects?.map((p) => [p.id, p]) ?? []),
    [projects],
  );

  const sortByPriority = (rows?: BacklogItemResponse[]) =>
    rows?.slice().sort((a, b) => (a.priority ?? 999) - (b.priority ?? 999));

  const activeRows = useMemo(() => sortByPriority(active.data), [active.data]);
  const archivedRows = useMemo(() => sortByPriority(archived.data), [archived.data]);

  const { data: employees = [] } = useEmployees();
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

  const handleDragEnd = useCallback(
    ({ active: draggingActive, over }: DragEndEvent) => {
      if (!over || draggingActive.id === over.id || !activeRows) return;
      const oldIndex = activeRows.findIndex((i) => i.id === draggingActive.id);
      const newIndex = activeRows.findIndex((i) => i.id === over.id);
      if (oldIndex === -1 || newIndex === -1) return;
      const newPriority = newIndex + 1;
      update.mutate({ id: String(draggingActive.id), data: { priority: newPriority } });
    },
    [activeRows, update],
  );

  const openCreate = () => { setEditing(null); setManualOpen(true); };
  const openEdit = (item: BacklogItemResponse) => { setEditing(item); setManualOpen(true); };
  const openLink = (item: BacklogItemResponse) => { setLinkTarget(item); setLinkOpen(true); };

  const patch = (id: string, data: Parameters<typeof update.mutate>[0]['data']) => {
    update.mutate(
      { id, data },
      { onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }) },
    );
  };

  const handleRefreshFromJira = () => {
    refreshFromJira.mutate(undefined, {
      onSuccess: (res) => {
        notification.success({
          title: 'Обновлено из Jira',
          description:
            `Перечитано: ${res.jira_refreshed} · ` +
            `Создано: ${res.created} · Обновлено: ${res.updated} · ` +
            `Архивировано: ${res.archived} · Восстановлено: ${res.restored}`,
        });
      },
      onError: (e) =>
        notification.error({ title: 'Ошибка', description: (e as Error).message }),
    });
  };

  const renderRoleEstimate = (
    field: 'estimate_analyst_hours' | 'estimate_dev_hours' | 'estimate_qa_hours' | 'estimate_opo_hours',
    editable: boolean,
  ) => (v: number | null, r: BacklogItemResponse) => {
    if (!editable || r.issue_id) return <span style={{ color: '#8faec8' }}>{v ?? '—'}</span>;
    return (
      <InputNumber
        size="small"
        min={0}
        value={v ?? undefined}
        variant="borderless"
        style={{ width: 70 }}
        onBlur={(e) => {
          const raw = e.currentTarget.value.trim();
          const next = raw === '' ? null : Number(raw);
          if (next === v) return;
          patch(r.id, { [field]: next as number } as Parameters<typeof update.mutate>[0]['data']);
        }}
      />
    );
  };

  const renderImpactRisk = (field: 'impact' | 'risk', editable: boolean) =>
    (v: BacklogImpactRisk | null, r: BacklogItemResponse) => {
      if (!editable || r.issue_id) {
        return v ? <Tag color={IMPACT_RISK_COLOR[v]}>{IMPACT_RISK_LABEL[v]}</Tag> : <span>—</span>;
      }
      return (
        <Select
          size="small"
          allowClear
          variant="borderless"
          value={v ?? undefined}
          style={{ width: 100 }}
          options={IMPACT_RISK_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
          onChange={(next) => patch(r.id, { [field]: next as BacklogImpactRisk } as Parameters<typeof update.mutate>[0]['data'])}
        />
      );
    };

  const baseColumns = (editable: boolean) => [
    {
      title: 'Prio', dataIndex: 'priority', width: 70, fixed: 'left' as const,
      render: (v: number | null, r: BacklogItemResponse) =>
        editable ? (
          <InputNumber
            size="small"
            min={1}
            value={v ?? undefined}
            variant="borderless"
            style={{ width: 55 }}
            onBlur={(e) => {
              const raw = e.currentTarget.value.trim();
              const next = raw === '' ? null : Number(raw);
              if (next === v) return;
              patch(r.id, { priority: next as number });
            }}
          />
        ) : (
          <span style={{ color: '#8faec8' }}>{v ?? '—'}</span>
        ),
    },
    {
      title: 'Идея', dataIndex: 'title',
      render: (v: string, r: BacklogItemResponse) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{v}</Typography.Text>
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
          return <span style={{ fontSize: 12, color: '#8faec8' }}>{r.assignee_display_name ?? '—'}</span>;
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
              color: '#8faec8',
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
        if (!r.jira_status) return <span style={{ color: '#8faec8' }}>—</span>;
        const days = daysSince(r.jira_status_changed_at);
        let ageColor: string = DARK_THEME.textMuted;
        if (days !== null) {
          if (days >= 365) ageColor = '#ff7875';
          else if (days >= 180) ageColor = DARK_THEME.yellow;
        }
        return (
          <Space direction="vertical" size={0} style={{ lineHeight: 1.1 }}>
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
    { title: 'АН ч', dataIndex: 'estimate_analyst_hours', width: 80,
      render: renderRoleEstimate('estimate_analyst_hours', editable) },
    { title: 'ПР ч', dataIndex: 'estimate_dev_hours', width: 80,
      render: renderRoleEstimate('estimate_dev_hours', editable) },
    { title: 'ТС ч', dataIndex: 'estimate_qa_hours', width: 80,
      render: renderRoleEstimate('estimate_qa_hours', editable) },
    { title: 'ОПЭ ч', dataIndex: 'estimate_opo_hours', width: 80,
      render: renderRoleEstimate('estimate_opo_hours', editable) },
    {
      title: 'ОПЭ→АН', dataIndex: 'opo_analyst_ratio', width: 90,
      render: (v: number | null, r: BacklogItemResponse) => {
        if (!editable) {
          return <span style={{ color: '#8faec8' }}>{v ?? '—'}</span>;
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
              <div style={{ fontSize: 10, color: '#4a6a80', marginTop: 1 }}>
                {pct}% ресурса
              </div>
            )}
          </div>
        );
      },
    },
    { title: 'Impact', dataIndex: 'impact', width: 110,
      render: renderImpactRisk('impact', editable) },
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

  const activeTable = (
    <DndContext
      collisionDetection={closestCenter}
      modifiers={[restrictToVerticalAxis]}
      onDragEnd={handleDragEnd}
    >
      <SortableContext items={activeRows?.map((i) => i.id) ?? []} strategy={verticalListSortingStrategy}>
        <Table<BacklogItemResponse>
          dataSource={activeRows}
          rowKey="id"
          loading={active.isLoading}
          pagination={false}
          size="small"
          scroll={{ x: 1400 }}
          components={{ body: { row: SortableRow } }}
          columns={[
            { title: '', width: 32, fixed: 'left' as const, render: (_, r) => <DragHandle id={r.id} /> },
            ...baseColumns(true),
            { title: 'Действия', width: 210, fixed: 'right' as const, render: (_, r) => actionsActive(r) },
          ]}
        />
      </SortableContext>
    </DndContext>
  );

  const archivedTable = (
    <Table<BacklogItemResponse>
      dataSource={archivedRows}
      rowKey="id"
      loading={archived.isLoading}
      pagination={false}
      size="small"
      scroll={{ x: 1400 }}
      columns={[
        ...baseColumns(false),
        { title: 'Действия', width: 160, fixed: 'right' as const, render: (_, r) => actionsArchived(r) },
      ]}
    />
  );

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <PageHeader
        eyebrow="Планирование"
        title="Бэклог инициатив"
        subtitle='Активные кандидаты — в основной вкладке; задачи в работе и архив — в отдельных'
        actions={
          <Space>
            <Button
              icon={<ReloadOutlined />}
              onClick={handleRefreshFromJira}
              loading={refreshFromJira.isPending}
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

      <Tabs
        activeKey={view}
        onChange={(k) => {
          const next = new URLSearchParams(searchParams);
          next.set('view', k);
          setSearchParams(next, { replace: true });
        }}
        items={[
          {
            key: 'active',
            label: `Активные (${activeRows?.length ?? 0})`,
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
