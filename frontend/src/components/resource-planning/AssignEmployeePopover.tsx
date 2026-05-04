import { Button, Popover, Select, Space, App } from 'antd';
import { useState } from 'react';
import { usePatchAssignment, useComputeResourcePlan } from '../../hooks/useResourcePlanning';
import type { EmployeeResponse } from '../../types/api';

interface Props {
  assignmentId: string;
  planId: string;
  phase: 'analyst' | 'dev' | 'qa' | 'opo';
  currentEmployeeId: string | null;
  employees: EmployeeResponse[];
  isPinned: boolean;
  children: React.ReactNode;
}

export default function AssignEmployeePopover({
  assignmentId,
  planId,
  phase,
  currentEmployeeId,
  employees,
  isPinned,
  children,
}: Props) {
  const { message } = App.useApp();
  const [open, setOpen] = useState(false);
  const [empId, setEmpId] = useState<string | null>(currentEmployeeId);
  const patch = usePatchAssignment();
  const compute = useComputeResourcePlan();

  // QA — без сотрудника, не показываем popover
  if (phase === 'qa') return <>{children}</>;

  const handleSave = async () => {
    if (!empId || empId === currentEmployeeId) {
      setOpen(false);
      return;
    }
    try {
      await patch.mutateAsync({ planId, assignmentId, data: { employee_id: empId } });
      await compute.mutateAsync(planId);
      message.success('Сотрудник закреплён, план пересчитан');
      setOpen(false);
    } catch {
      message.error('Ошибка пересчёта');
    }
  };

  const content = (
    <Space direction="vertical" style={{ minWidth: 260 }}>
      <Select
        value={empId}
        onChange={setEmpId}
        showSearch
        optionFilterProp="label"
        style={{ width: '100%' }}
        placeholder="Выбрать сотрудника"
        options={employees.map(e => ({
          label: `${e.display_name}${e.role ? ` (${e.role})` : ''}`,
          value: e.id,
        }))}
      />
      <Space>
        <Button
          size="small"
          type="primary"
          onClick={handleSave}
          loading={patch.isPending || compute.isPending}
        >
          Закрепить + пересчитать
        </Button>
        <Button size="small" onClick={() => setOpen(false)}>Отмена</Button>
      </Space>
      {isPinned && (
        <span style={{ fontSize: 11, color: '#00c9c8' }}>● закреплено</span>
      )}
    </Space>
  );

  return (
    <Popover
      content={content}
      title="Назначить сотрудника"
      trigger="click"
      open={open}
      onOpenChange={setOpen}
      placement="top"
    >
      {children}
    </Popover>
  );
}
