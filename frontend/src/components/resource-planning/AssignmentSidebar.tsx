import { useMemo, useState } from 'react';
import { Alert, App, Button, DatePicker, Descriptions, Divider, Drawer, Modal, Select, Space, Spin, Table, Tag, Typography } from 'antd';
import dayjs from 'dayjs';

import type {
  AssignmentExplainConflict,
  AssignmentExplainResponseV2,
  AssignmentOut,
  EmployeeChangePreviewResponse,
  ManualEditFlag,
} from '../../api/resourcePlanning';
import {
  clearAssignmentManualEdit,
  mergeAssignment,
  patchAssignment,
  previewEmployeeChange,
} from '../../api/resourcePlanning';
import { useExplainAssignment } from '../../hooks/useResourcePlanning';
import { useRpPreferences } from '../../hooks/useRpPreferences';
import type { EmployeeResponse } from '../../types/api';
import { PHASE_LABELS } from '../../utils/gantt';
import EmployeeAvatar from './EmployeeAvatar';
import AbsencesSection from './sidebar/AbsencesSection';
import AlgorithmSection from './sidebar/AlgorithmSection';
import CriticalPathSection from './sidebar/CriticalPathSection';
import DailyBreakdownSection from './sidebar/DailyBreakdownSection';
import HoursSummarySection from './sidebar/HoursSummarySection';
import PhaseCalcSection from './sidebar/PhaseCalcSection';
import SectionVisibilityPopover from './sidebar/SectionVisibilityPopover';
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
  const [pendingEmpChange, setPendingEmpChange] = useState<{
    employeeId: string;
    preview: EmployeeChangePreviewResponse;
  } | null>(null);
  const { prefs, patch: patchPrefs } = useRpPreferences();

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
        styles={{ wrapper: { width: 920 } }}
        mask
        maskClosable
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

  const handleEmployeeChange = async (newEmpId: string) => {
    if (!newEmpId || newEmpId === assignment.employee_id) return;
    setSaving(true);
    try {
      const preview = await previewEmployeeChange(planId, assignment.id, newEmpId);
      if (preview.has_conflicts) {
        setPendingEmpChange({ employeeId: newEmpId, preview });
        setSaving(false);
        return;
      }
      // Без конфликтов — сразу применяем
      await patchAssignment(planId, assignment.id, { employee_id: newEmpId });
      onChanged?.();
    } catch (e) {
      message.error((e as Error).message || 'Ошибка');
    } finally {
      setSaving(false);
    }
  };

  const confirmEmployeeChange = async () => {
    if (!pendingEmpChange) return;
    setSaving(true);
    try {
      await patchAssignment(planId, assignment.id, {
        employee_id: pendingEmpChange.employeeId,
        force: true,
      });
      setPendingEmpChange(null);
      message.success('Сотрудник заменён, план пересчитан');
      onChanged?.();
    } catch (e) {
      message.error((e as Error).message || 'Ошибка пересчёта');
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

  const handleClearManual = async (flags?: ManualEditFlag[]) => {
    setSaving(true);
    try {
      await clearAssignmentManualEdit(planId, assignment.id, flags);
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
      styles={{ wrapper: { width: 920 } }}
      mask
      maskClosable
      title={
        <Space style={{ width: '100%', justifyContent: 'space-between' }}>
          <Space>
            <span>{PHASE_LABELS[assignment.phase] ?? assignment.phase}</span>
            {assignment.is_pinned && <Tag color="cyan">Закреплено</Tag>}
            {assignment.is_on_critical_path && <Tag color="red">Критический путь</Tag>}
            {assignment.out_of_quarter && <Tag color="orange">Вне квартала</Tag>}
          </Space>
          <SectionVisibilityPopover
            visible={prefs.detail_sections_visible}
            onChange={(next) => patchPrefs({ detail_sections_visible: next })}
          />
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
              onChange={(empId) => handleEmployeeChange(empId)}
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
      <Space orientation="vertical" style={{ width: '100%' }}>
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
        {assignment.pinned_employee && (
          <Button
            block
            danger
            onClick={() => handleClearManual(['employee'])}
            disabled={saving}
          >
            Сбросить закреплённого исполнителя
          </Button>
        )}
        {assignment.pinned_start ? (
          <Button
            block
            danger
            onClick={() => updateField({ pinned_start: false })}
            disabled={saving}
          >
            Снять фиксацию даты
          </Button>
        ) : (
          <Button
            block
            onClick={() => updateField({ pinned_start: true })}
            disabled={saving}
          >
            Зафиксировать дату
          </Button>
        )}
        {assignment.pinned_split && hasSiblings && (
          <Button
            block
            danger
            onClick={() => handleClearManual(['split'])}
            disabled={saving}
          >
            Сбросить признак разбивки
          </Button>
        )}
        {assignment.is_pinned && (
          <Button block onClick={() => handleClearManual()} disabled={saving}>
            Снять все ручные правки
          </Button>
        )}
      </Space>

      <DetailSections planId={planId} assignment={assignment} prefs={prefs} patchPrefs={patchPrefs} />

      <SplitAssignmentModal
        open={splitOpen}
        onClose={() => setSplitOpen(false)}
        planId={planId}
        assignment={assignment}
        onSplit={onChanged}
      />

      <Modal
        open={!!pendingEmpChange}
        onCancel={() => setPendingEmpChange(null)}
        onOk={confirmEmployeeChange}
        okText="Всё равно сохранить и пересчитать"
        cancelText="Отмена"
        okButtonProps={{ danger: true, loading: saving }}
        width={720}
        title={
          <Space>
            <Tag color="orange">Конфликты</Tag>
            <span>Новый сотрудник: {pendingEmpChange?.preview.new_employee_name ?? '—'}</span>
          </Space>
        }
      >
        {pendingEmpChange && (
          <Space orientation="vertical" style={{ width: '100%' }} size={12}>
            <Alert
              type="warning"
              showIcon
              title="При подтверждении план будет пересчитан. Другие фазы этого сотрудника могут сдвинуться, чтобы разрулить перегрузки и обойти отпуска."
            />
            {pendingEmpChange.preview.absences.length > 0 && (
              <>
                <Typography.Text strong>Отпуска / отсутствия в окне фазы ({pendingEmpChange.preview.absences.length})</Typography.Text>
                <Table
                  size="small"
                  pagination={false}
                  rowKey={(_, i) => `abs-${i}`}
                  dataSource={pendingEmpChange.preview.absences}
                  columns={[
                    { title: 'Начало', dataIndex: 'start_date', width: 110 },
                    { title: 'Окончание', dataIndex: 'end_date', width: 110 },
                    { title: 'Причина', dataIndex: 'reason', render: (v) => v ?? '—' },
                    { title: 'Пересечение', dataIndex: 'overlap_days', width: 110, render: (v) => `${v} д.` },
                  ]}
                />
              </>
            )}
            {pendingEmpChange.preview.overloads.length > 0 && (
              <>
                <Typography.Text strong>Перегрузки с другими фазами ({pendingEmpChange.preview.overloads.length})</Typography.Text>
                <Table
                  size="small"
                  pagination={false}
                  rowKey={(_, i) => `ovl-${i}`}
                  dataSource={pendingEmpChange.preview.overloads}
                  columns={[
                    { title: 'День', dataIndex: 'date', width: 110 },
                    {
                      title: 'Другая задача',
                      render: (_, r) => `${r.other_backlog_item_key ?? '—'} · ${r.other_backlog_item_title}`,
                    },
                    { title: 'Фаза', dataIndex: 'other_phase', width: 90 },
                    {
                      title: 'Итого ч/день',
                      dataIndex: 'hours_on_day',
                      width: 110,
                      render: (v: number) => (
                        <span style={{ color: v > 10 ? '#ef4444' : '#ffb432', fontWeight: 700 }}>
                          {v.toFixed(1)} ч
                        </span>
                      ),
                    },
                  ]}
                />
              </>
            )}
          </Space>
        )}
      </Modal>
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
  const conflicts = (data.conflicts ?? []).filter(c => c.severity !== 'info');
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
      <Space orientation="vertical" style={{ width: '100%' }} size={8}>
        {onCp && (
          <Alert
            type="error"
            showIcon
            title={<span>Фаза на критическом пути. Резерв: <b>{slack.toFixed(0)} д.</b> Сдвиг сорвёт срок проекта.</span>}
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
      title={
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

interface DetailSectionsProps {
  planId: string;
  assignment: AssignmentOut;
  prefs: ReturnType<typeof useRpPreferences>['prefs'];
  patchPrefs: ReturnType<typeof useRpPreferences>['patch'];
}

function DetailSections({ planId, assignment, prefs, patchPrefs }: DetailSectionsProps) {
  const { data } = useExplainAssignment(planId, assignment.id, true) as { data: AssignmentExplainResponseV2 | undefined };

  const isVisible = (k: string) => prefs.detail_sections_visible[k] !== false;
  const isCollapsed = (k: string) => !!prefs.detail_sections_collapsed[k];
  const toggleCollapse = (key: string) => {
    patchPrefs({
      detail_sections_collapsed: {
        ...prefs.detail_sections_collapsed,
        [key]: !prefs.detail_sections_collapsed[key],
      },
    });
  };

  // Resolve assignment from explain data (has full fields like daily_hours, out_of_quarter)
  // Fall back to the prop assignment for critical path display if data not yet loaded.
  const resolvedAssignment = data?.assignment ?? assignment;

  return (
    <>
      <Divider>Детализация</Divider>

      {isVisible('algorithm') && (
        <AlgorithmSection
          log={data?.algorithm_log ?? []}
          collapsed={isCollapsed('algorithm')}
          onToggleCollapse={() => toggleCollapse('algorithm')}
        />
      )}

      {isVisible('day_table') && (
        <DailyBreakdownSection
          items={data?.daily_breakdown ?? []}
          collapsed={isCollapsed('day_table')}
          onToggleCollapse={() => toggleCollapse('day_table')}
          involvementPct={data?.phase_calc?.involvement_pct ?? null}
        />
      )}

      {isVisible('absences') && (
        <AbsencesSection
          items={data?.absences_in_window ?? []}
          collapsed={isCollapsed('absences')}
          onToggleCollapse={() => toggleCollapse('absences')}
        />
      )}

      {isVisible('sources') && (
        <PhaseCalcSection
          data={data?.phase_calc ?? null}
          collapsed={isCollapsed('sources')}
          onToggleCollapse={() => toggleCollapse('sources')}
        />
      )}

      {isVisible('duration') && (
        <HoursSummarySection
          data={data?.hours_summary ?? null}
          collapsed={isCollapsed('duration')}
          onToggleCollapse={() => toggleCollapse('duration')}
        />
      )}

      {isVisible('critical_path') && (
        <CriticalPathSection
          assignment={resolvedAssignment}
          collapsed={isCollapsed('critical_path')}
          onToggleCollapse={() => toggleCollapse('critical_path')}
        />
      )}
    </>
  );
}
