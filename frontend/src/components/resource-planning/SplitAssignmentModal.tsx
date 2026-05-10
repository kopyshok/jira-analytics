import { useEffect, useState } from 'react';
import { App, Button, Checkbox, InputNumber, Modal, Space, Typography } from 'antd';

import type { AssignmentOut } from '../../api/resourcePlanning';
import { splitAssignment } from '../../api/resourcePlanning';

interface Props {
  open: boolean;
  onClose: () => void;
  onSplit?: () => void;
  planId: string;
  assignment: AssignmentOut | null;
}

export default function SplitAssignmentModal({ open, onClose, onSplit, planId, assignment }: Props) {
  const { message } = App.useApp();
  const total = assignment?.hours_allocated ?? 0;
  const [parts, setParts] = useState<number[]>([Math.round(total / 2), Math.round(total - total / 2)]);
  const [cascade, setCascade] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open && assignment) {
      const half = Math.round((assignment.hours_allocated ?? 0) / 2);
      setParts([half, (assignment.hours_allocated ?? 0) - half]);
      setCascade(true);
    }
  }, [open, assignment]);

  const sum = parts.reduce((s, n) => s + (Number(n) || 0), 0);
  const valid = parts.length >= 2 && parts.every(n => n > 0) && Math.abs(sum - total) < 0.01;

  const updatePart = (idx: number, value: number | null) => {
    const next = [...parts];
    next[idx] = Number(value) || 0;
    setParts(next);
  };

  const addPart = () => {
    if (parts.length >= 10) return;
    setParts([...parts, 0]);
  };

  const removePart = (idx: number) => {
    if (parts.length <= 2) return;
    setParts(parts.filter((_, i) => i !== idx));
  };

  const submit = async () => {
    if (!assignment || !valid) return;
    setSaving(true);
    try {
      await splitAssignment(planId, assignment.id, { parts, cascade });
      message.success(`Фаза разбита на ${parts.length} ${parts.length > 4 ? 'частей' : 'части'}`);
      onSplit?.();
      onClose();
    } catch (e) {
      message.error((e as Error).message || 'Ошибка разбиения');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      title="Разбить фазу на части"
      open={open}
      onCancel={onClose}
      onOk={submit}
      okText="Разбить"
      cancelText="Отмена"
      confirmLoading={saving}
      okButtonProps={{ disabled: !valid }}
    >
      {assignment && (
        <Space direction="vertical" style={{ width: '100%' }}>
          <Typography.Text type="secondary">
            {assignment.backlog_item_title} · фаза «{assignment.phase}» · всего {total.toFixed(0)} ч
          </Typography.Text>
          <Space direction="vertical" style={{ width: '100%' }}>
            {parts.map((h, idx) => (
              <Space key={idx} align="center">
                <span style={{ width: 60 }}>Часть {idx + 1}</span>
                <InputNumber
                  min={0}
                  step={1}
                  value={h}
                  onChange={(v) => updatePart(idx, v as number | null)}
                  addonAfter="ч"
                />
                {parts.length > 2 && (
                  <Button size="small" danger onClick={() => removePart(idx)}>
                    Удалить
                  </Button>
                )}
              </Space>
            ))}
            <Button size="small" onClick={addPart} disabled={parts.length >= 10}>
              + добавить часть
            </Button>
          </Space>
          <Typography.Text type={Math.abs(sum - total) < 0.01 ? 'success' : 'danger'}>
            Сумма: {sum.toFixed(0)} ч (требуется {total.toFixed(0)} ч)
          </Typography.Text>
          <Checkbox checked={cascade} onChange={(e) => setCascade(e.target.checked)}>
            Разбить и последующие фазы пропорционально
          </Checkbox>
        </Space>
      )}
    </Modal>
  );
}
