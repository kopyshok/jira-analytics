import { useCallback, useMemo, useState } from 'react';
import {
  App, Button, InputNumber, Popconfirm, Select, Space, Table, Tag, Tooltip, Typography,
} from 'antd';
import {
  DeleteOutlined, DisconnectOutlined, EditOutlined, HolderOutlined, LinkOutlined,
  PlusOutlined, ReloadOutlined,
} from '@ant-design/icons';
import { DndContext, closestCenter, type DragEndEvent } from '@dnd-kit/core';
import { SortableContext, useSortable, verticalListSortingStrategy } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { restrictToVerticalAxis } from '@dnd-kit/modifiers';
import QuarterYearSelect from '../components/shared/QuarterYearSelect';
import PageHeader from '../components/shared/PageHeader';
import BacklogManualModal from '../components/backlog/BacklogManualModal';
import BacklogLinkJiraModal from '../components/backlog/BacklogLinkJiraModal';
import {
  useBacklogItems, useUpdateBacklogItem, useDeleteBacklogItem, useProjects,
  useUnlinkJira, useRefreshFromJira,
} from '../hooks/useBacklog';
import { useJiraSettings } from '../hooks/useSettings';
import { useQuarterYear } from '../hooks/useQuarterYear';
import type { BacklogItemResponse, BacklogImpactRisk } from '../types/api';

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
  const { year, quarter } = useQuarterYear();
  const { data, isLoading } = useBacklogItems(year, `Q${quarter}`);
  const { data: projects } = useProjects();
  const jiraSettings = useJiraSettings();
  const jiraBaseUrl = jiraSettings.data?.base_url ?? '';

  const update = useUpdateBacklogItem();
  const del = useDeleteBacklogItem();
  const unlink = useUnlinkJira();
  const refreshFromJira = useRefreshFromJira();

  const [manualOpen, setManualOpen] = useState(false);
  const [editing, setEditing] = useState<BacklogItemResponse | null>(null);
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkTarget, setLinkTarget] = useState<BacklogItemResponse | null>(null);

  const projectMap = useMemo(
    () => new Map(projects?.map((p) => [p.id, p]) ?? []),
    [projects],
  );

  const sorted = useMemo(
    () => data?.slice().sort((a, b) => (a.priority ?? 999) - (b.priority ?? 999)),
    [data],
  );

  const handleDragEnd = useCallback(
    ({ active, over }: DragEndEvent) => {
      if (!over || active.id === over.id || !sorted) return;
      const oldIndex = sorted.findIndex((i) => i.id === active.id);
      const newIndex = sorted.findIndex((i) => i.id === over.id);
      if (oldIndex === -1 || newIndex === -1) return;
      const newPriority = newIndex + 1;
      update.mutate({ id: String(active.id), data: { priority: newPriority } });
    },
    [sorted, update],
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
          description: `Создано: ${res.created} · Обновлено: ${res.updated} · Удалено: ${res.removed}`,
        });
      },
      onError: (e) =>
        notification.error({ title: 'Ошибка', description: (e as Error).message }),
    });
  };

  const renderRoleEstimate = (
    field: 'estimate_analyst_hours' | 'estimate_dev_hours' | 'estimate_qa_hours' | 'estimate_opo_hours',
  ) => (v: number | null, r: BacklogItemResponse) => {
    if (r.issue_id) return <span style={{ color: '#8faec8' }}>{v ?? '—'}</span>;
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

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <PageHeader
        eyebrow="Планирование"
        title="Бэклог квартала"
        subtitle="Инициативы: авто-синк из Jira (категория «Бэклог инициатив») + ручные идеи · drag-n-drop для приоритета"
        actions={
          <Space>
            <QuarterYearSelect />
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

      <DndContext collisionDetection={closestCenter} modifiers={[restrictToVerticalAxis]} onDragEnd={handleDragEnd}>
        <SortableContext items={sorted?.map((i) => i.id) ?? []} strategy={verticalListSortingStrategy}>
          <Table<BacklogItemResponse>
            dataSource={sorted}
            rowKey="id"
            loading={isLoading}
            pagination={false}
            size="small"
            scroll={{ x: 1280 }}
            components={{ body: { row: SortableRow } }}
            columns={[
              {
                title: '', width: 32, fixed: 'left',
                render: (_, r) => <DragHandle id={r.id} />,
              },
              {
                title: 'Prio', dataIndex: 'priority', width: 70, fixed: 'left',
                render: (v: number | null, r) => (
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
                ),
              },
              {
                title: 'Идея', dataIndex: 'title',
                render: (v: string, r) => (
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
              { title: 'АН ч', dataIndex: 'estimate_analyst_hours', width: 80,
                render: renderRoleEstimate('estimate_analyst_hours') },
              { title: 'ПР ч', dataIndex: 'estimate_dev_hours', width: 80,
                render: renderRoleEstimate('estimate_dev_hours') },
              { title: 'ТС ч', dataIndex: 'estimate_qa_hours', width: 80,
                render: renderRoleEstimate('estimate_qa_hours') },
              { title: 'ОПЭ ч', dataIndex: 'estimate_opo_hours', width: 80,
                render: renderRoleEstimate('estimate_opo_hours') },
              {
                title: 'ОПЭ→АН', dataIndex: 'opo_analyst_ratio', width: 90,
                render: (v: number | null, r) => (
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
                ),
              },
              {
                title: 'Impact', dataIndex: 'impact', width: 110,
                render: (v: BacklogImpactRisk | null, r) => {
                  if (r.issue_id) {
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
                      onChange={(next) => patch(r.id, { impact: next as BacklogImpactRisk })}
                    />
                  );
                },
              },
              {
                title: 'Risk', dataIndex: 'risk', width: 110,
                render: (v: BacklogImpactRisk | null, r) => {
                  if (r.issue_id) {
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
                      onChange={(next) => patch(r.id, { risk: next as BacklogImpactRisk })}
                    />
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
              {
                title: 'Q', width: 90,
                render: (_, r) => (
                  <span style={{ fontFamily: 'monospace', color: '#c5d8ee' }}>
                    {r.year ?? '—'} {r.quarter ?? ''}
                  </span>
                ),
              },
              {
                title: 'Действия', width: 170, fixed: 'right',
                render: (_, r) => (
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
                      title="Удалить идею?"
                      onConfirm={() => del.mutate(r.id, {
                        onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }),
                      })}
                    >
                      <Button icon={<DeleteOutlined />} size="small" danger />
                    </Popconfirm>
                  </Space>
                ),
              },
            ]}
          />
        </SortableContext>
      </DndContext>
    </Space>
  );
}
