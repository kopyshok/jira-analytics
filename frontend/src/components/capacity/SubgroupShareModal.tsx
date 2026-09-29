import { useState } from 'react';
import { App, DatePicker, InputNumber, Modal, Select, Space, Typography } from 'antd';
import dayjs, { Dayjs } from 'dayjs';

import { usePutSubgroupShare } from '../../hooks/useTeamRegistry';

const { Text } = Typography;

interface Props {
  employeeId: string;
  team: string;
  subgroups: { id: string; name: string }[];
  /** transfer — одна группа 100 %, split — проценты по группам. */
  mode: 'transfer' | 'split';
  onClose: () => void;
}

export default function SubgroupShareModal({ employeeId, team, subgroups, mode, onClose }: Props) {
  const { message } = App.useApp();
  const put = usePutSubgroupShare();
  const [on, setOn] = useState<Dayjs | null>(dayjs());
  const [group, setGroup] = useState<string | null>(null);
  const [pct, setPct] = useState<Record<string, number | null>>({});

  const shares = mode === 'transfer'
    ? (group ? [{ subgroup_id: group, percent: 100 }] : [])
    : Object.entries(pct)
        .filter(([, v]) => (v ?? 0) > 0)
        .map(([subgroup_id, v]) => ({ subgroup_id, percent: v as number }));
  const total = shares.reduce((s, x) => s + x.percent, 0);
  const valid = !!on && shares.length > 0 && total === 100
    && (mode === 'transfer' || shares.length >= 2);

  const handleOk = async () => {
    try {
      await put.mutateAsync({
        employeeId, team, valid_from: on!.format('YYYY-MM-DD'), shares,
      });
      message.success(mode === 'transfer' ? 'Сотрудник переведён' : 'Распределение сохранено');
      onClose();
    } catch (e) {
      message.error((e as Error).message || 'Не удалось сохранить');
    }
  };

  return (
    <Modal
      open
      title={mode === 'transfer' ? 'Перевести в группу' : 'Разделить между группами'}
      onOk={handleOk}
      onCancel={onClose}
      okText="Сохранить"
      cancelText="Отмена"
      okButtonProps={{ disabled: !valid }}
      confirmLoading={put.isPending}
      destroyOnHidden
    >
      <Space orientation="vertical" style={{ width: '100%' }}>
        <Text type="secondary">С даты</Text>
        <DatePicker value={on} onChange={setOn} format="DD.MM.YYYY" style={{ width: '100%' }} />
        {mode === 'transfer' ? (
          <>
            <Text type="secondary">Новая группа</Text>
            <Select
              placeholder="Группа"
              value={group}
              onChange={setGroup}
              options={subgroups.map((g) => ({ value: g.id, label: g.name }))}
              style={{ width: '100%' }}
            />
          </>
        ) : (
          <>
            {subgroups.map((g) => (
              <Space key={g.id} style={{ justifyContent: 'space-between', width: '100%' }}>
                <span>{g.name}</span>
                <InputNumber
                  min={0} max={100} precision={0} suffix="%"
                  value={pct[g.id] ?? null}
                  onChange={(v) => setPct((p) => ({ ...p, [g.id]: v }))}
                />
              </Space>
            ))}
            <Text type={total === 100 && shares.length >= 2 ? 'secondary' : 'danger'}>
              Итого {total}% — нужно 100%{shares.length < 2 ? ', хотя бы на две группы' : ''}
            </Text>
          </>
        )}
        <Text type="secondary">
          До этой даты часы остаются в прежней группе, с неё — идут по новому распределению.
          Утверждённые сценарии не меняются: в них появится отметка о расхождении.
        </Text>
      </Space>
    </Modal>
  );
}
