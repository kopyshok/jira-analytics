import { useMemo, useState } from 'react';
import { App, Button, DatePicker, Descriptions, Divider, Drawer, Select, Space, Tag, Typography } from 'antd';
import dayjs from 'dayjs';

import type { AssignmentOut } from '../../api/resourcePlanning';
import {
  clearAssignmentManualEdit,
  mergeAssignment,
  patchAssignment,
} from '../../api/resourcePlanning';
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
    return <Drawer open={open} onClose={onClose} width={420} title="Назначение" />;
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
      width={420}
      title={
        <Space>
          <span>{PHASE_LABELS[assignment.phase] ?? assignment.phase}</span>
          {assignment.is_pinned && <Tag color="cyan">Закреплено</Tag>}
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
