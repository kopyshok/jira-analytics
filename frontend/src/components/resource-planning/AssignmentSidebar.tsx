import { useMemo, useState } from 'react';
import { Alert, App, Button, DatePicker, Descriptions, Divider, Drawer, Select, Space, Spin, Tag, Typography } from 'antd';
import dayjs from 'dayjs';

import type { AssignmentExplainConflict, AssignmentOut } from '../../api/resourcePlanning';
import {
  clearAssignmentManualEdit,
  mergeAssignment,
  patchAssignment,
} from '../../api/resourcePlanning';
import { useExplainAssignment } from '../../hooks/useResourcePlanning';
import type { EmployeeResponse } from '../../types/api';
import { PHASE_LABELS } from '../../utils/gantt';
import EmployeeAvatar from './EmployeeAvatar';
import SplitAssignmentModal from './SplitAssignmentModal';

interface Props {
  open: boolean;
  onClose: () => void;
  planId: string;
  assignment: AssignmentOut | null;
  allAssignments: AssignmentOut[];
  employees: EmployeeResponse[];
  onChanged?: () => void;
}

export default function AssignmentSidebar({
  open,
  onClose,
  planId,
  assignment,
  allAssignments,
  employees,
  onChanged,
}: Props) {
  const { message } = App.useApp();
  const [saving, setSaving] = useState(false);
  const [splitOpen, setSplitOpen] = useState(false);

  const sameItemAssignments = useMemo(
    () => (assignment ? allAssignments.filter(a => a.backlog_item_id === assignment.backlog_item_id && a.id !== assignment.id) : []),
    [assignment, allAssignments],
  );

  const hasSiblings = useMemo(
    () =>
      assignment
        ? allAssignments.filter(
            a =>
              a.backlog_item_id === assignment.backlog_item_id &&
              a.phase === assignment.phase,
          ).length > 1
        : false,
    [assignment, allAssignments],
  );

  if (!assignment) {
    return (
      <Drawer
        open={open}
        onClose={onClose}
        width={920}
        mask={false}
        maskClosable={false}
        title="Назначение"
      />
    );
  }

  const updateField = async (data: Parameters<typeof patchAssignment>[2]) => {
    setSaving(true);
    try {
      await patchAssignment(planId, assignment.id, data);
      onChanged?.();
    } catch (e) {
      message.error((e as Error).message || 'Ошибка сохранения');
    } finally {
      setSaving(false);
    }
  };

  const handleMerge = async () => {
    setSaving(true);
    try {
      await mergeAssignment(planId, assignment.id);
      message.success('Части слиты');
      onChanged?.();
      onClose();
    } catch (e) {
      message.error((e as Error).message || 'Ошибка слияния');
    } finally {
      setSaving(false);
    }
  };

  const handleClearManual = async () => {
    setSaving(true);
    try {
      await clearAssignmentManualEdit(planId, assignment.id);
      message.success('Ручные правки сняты');
      onChanged?.();
    } catch (e) {
      message.error((e as Error).message || 'Ошибка');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Drawer
      open={open}
      onClose={onClose}
      width={920}
      mask={false}
      maskClosable={false}
      title={
        <Space>
          <span>{PHASE_LABELS[assignment.phase] ?? assignment.phase}</span>
          {assignment.is_pinned && <Tag color="cyan">Закреплено</Tag>}
          {assignment.is_on_critical_path && <Tag color="red">Критический путь</Tag>}
        </Space>
      }
    >
      <Typography.Title level={5} style={{ marginTop: 0 }}>
        {assignment.backlog_item_title}
      </Typography.Title>
      {assignment.backlog_item_key && (
        <Typography.Text type="secondary">{assignment.backlog_item_key}</Typography.Text>
      )}
      <Divider />
      <Descriptions size="small" column={1} bordered>
        <Descriptions.Item label="Часов">
          {assignment.hours_allocated?.toFixed(0) ?? '—'}
        </Descriptions.Item>
        <Descriptions.Item label="Часть">
          {assignment.part_number}
        </Descriptions.Item>
        <Descriptions.Item label="Сотрудник">
          {assignment.phase === 'qa' ? (
            <Typography.Text type="secondary">QA — без сотрудника</Typography.Text>
          ) : (
            <Select
              value={assignment.employee_id ?? undefined}
              placeholder="Не назначен"
              style={{ width: '100%' }}
              loading={saving}
              showSearch
              optionFilterProp="label"
              onChange={(empId) => updateField({ employee_id: empId })}
              options={employees.map((e) => ({
                value: e.id,
                label: e.display_name,
              }))}
            />
          )}
          {assignment.employee_name && (
            <Space style={{ marginTop: 6 }}>
              <EmployeeAvatar name={assignment.employee_name} role={assignment.employee_role} size={20} />
              <span style={{ fontSize: 12, color: '#8ab0d8' }}>{assignment.employee_name}</span>
            </Space>
          )}
        </Descriptions.Item>
        <Descriptions.Item label="Начало">
          <DatePicker
            value={assignment.start_date ? dayjs(assignment.start_date) : null}
            disabled={saving}
            allowClear={false}
            onChange={(d) => d && updateField({ start_date: d.format('YYYY-MM-DD') })}
          />
        </Descriptions.Item>
        <Descriptions.Item label="Окончание">
          <DatePicker
            value={assignment.end_date ? dayjs(assignment.end_date) : null}
            disabled={saving}
            allowClear={false}
            onChange={(d) => d && updateField({ end_date: d.format('YYYY-MM-DD') })}
          />
        </Descriptions.Item>
        <Descriptions.Item label="Предшественники">
          <Select
            mode="multiple"
            placeholder="Зависит от…"
            value={(assignment as AssignmentOut & { predecessor_ids?: string[] }).predecessor_ids ?? []}
            style={{ width: '100%' }}
            disabled={saving}
            onChange={(ids) => updateField({ predecessor_ids: ids })}
            options={sameItemAssignments.map((a) => ({
              value: a.id,
              label: `${PHASE_LABELS[a.phase] ?? a.phase}${a.part_number > 1 ? ` ч.${a.part_number}` : ''} — ${a.employee_name ?? '—'}`,
            }))}
          />
        </Descriptions.Item>
      </Descriptions>

      <AssignmentExplainSection planId={planId} assignmentId={assignment.id} />

      <Divider>Действия</Divider>
      <Space direction="vertical" style={{ width: '100%' }}>
        {!hasSiblings && assignment.phase !== 'qa' && (
          <Button block onClick={() => setSplitOpen(true)} disabled={saving}>
            Разбить на части
          </Button>
        )}
        {hasSiblings && (
          <Button block onClick={handleMerge} disabled={saving}>
            Слить части в одну
          </Button>
        )}
        {assignment.is_pinned && (
          <Button block danger onClick={handleClearManual} disabled={saving}>
            Снять ручные правки
          </Button>
        )}
      </Space>

      <SplitAssignmentModal
        open={splitOpen}
        onClose={() => setSplitOpen(false)}
        planId={planId}
        assignment={assignment}
        onSplit={onChanged}
      />
    </Drawer>
  );
}

function AssignmentExplainSection({ planId, assignmentId }: { planId: string; assignmentId: string }) {
  const { data, isLoading, isError } = useExplainAssignment(planId, assignmentId, true);
  if (isLoading) {
    return (
      <>
        <Divider>Расчёт проблем</Divider>
        <Spin size="small" />
      </>
    );
  }
  if (isError || !data) {
    return (
      <>
        <Divider>Расчёт проблем</Divider>
        <span style={{ color: '#ef4444', fontSize: 12 }}>Ошибка загрузки расчёта</span>
      </>
    );
  }
  const conflicts = data.conflicts ?? [];
  const onCp = data.assignment.is_on_critical_path;
  const slack = data.assignment.slack_days ?? 0;
  if (conflicts.length === 0 && !onCp) {
    return (
      <>
        <Divider>Расчёт проблем</Divider>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Конфликтов нет. Резерв: {slack.toFixed(0)} д.
        </Typography.Text>
      </>
    );
  }
  return (
    <>
      <Divider>Расчёт проблем</Divider>
      <Space direction="vertical" style={{ width: '100%' }} size={8}>
        {onCp && (
          <Alert
            type="error"
            showIcon
            message={<span>Фаза на критическом пути. Резерв: <b>{slack.toFixed(0)} д.</b> Сдвиг сорвёт срок проекта.</span>}
          />
        )}
        {conflicts.map(c => (
          <ConflictBlock key={c.id} c={c} />
        ))}
      </Space>
    </>
  );
}

function ConflictBlock({ c }: { c: AssignmentExplainConflict }) {
  const isOverload = c.type.startsWith('OVERLOAD_');
  const sev = c.severity === 'critical' ? 'error' : c.severity === 'warning' ? 'warning' : 'info';
  return (
    <Alert
      type={sev}
      showIcon
      message={
        <div style={{ width: '100%', fontSize: 12 }}>
          <div style={{ marginBottom: 6 }}>{c.message}</div>
          {isOverload && (
            <>
              <div style={{ marginBottom: 6, color: '#cfe1f5' }}>
                День <b>{c.date}</b> · Доступно <b>{(c.available_hours ?? 0).toFixed(1)} ч</b> ·
                Назначено <b>{(c.demand_hours ?? 0).toFixed(1)} ч</b> ·
                <span style={{ color: (c.overload_pct ?? 0) > 110 ? '#ef4444' : '#ffb432', fontWeight: 700, marginLeft: 4 }}>
                  {(c.overload_pct ?? 0).toFixed(0)}%
                </span>
              </div>
              {c.contributors.length > 0 && (
                <>
                  <div style={{ color: '#8ab0d8', fontSize: 11, marginBottom: 4 }}>
                    Перекрывают день ({c.contributors.length}):
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                    {c.contributors.map(co => (
                      <div
                        key={co.assignment_id}
                        style={{
                          display: 'grid',
                          gridTemplateColumns: '70px 90px 1fr 80px',
                          gap: 8,
                          fontSize: 11,
                          padding: '2px 0',
                          borderBottom: '1px dashed rgba(120,150,180,0.15)',
                        }}
                      >
                        <span style={{ color: '#7a9ab8' }}>{co.item_key ?? '—'}</span>
                        <span style={{ color: '#8ab0d8' }}>{co.phase_label}</span>
                        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {co.item_title}
                        </span>
                        <span style={{ textAlign: 'right', color: '#cfe1f5' }}>
                          {co.hours_per_day.toFixed(2)} ч/день
                        </span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </>
          )}
        </div>
      }
    />
  );
}
