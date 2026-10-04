import { useMemo, useState } from 'react';
import { App, Button, Modal, Select, Typography } from 'antd';

import { useEmployees } from '../../hooks/useCapacity';
import { useRoles } from '../../hooks/useRoles';
import { useAddPlanWatch } from '../../hooks/useResourcePlanning';
import { roleTeamPicks, watchPickerOptions } from '../../utils/rpWatch';

interface Props {
  open: boolean;
  onClose: () => void;
  planId: string;
  /** Люди плана и уже наблюдаемые — находятся поиском, но выбрать их нельзя. */
  planIds: string[];
  watchedIds: string[];
  /** Квартал плана (ISO, включительно): «вся роль в команде» — состав за квартал. */
  quarterStart: string;
  quarterEnd: string;
}

/** Окно «Подобрать людей»: сотрудники любых команд — по ФИО или всей ролью в команде.
 *  Монтируется только открытым — список сотрудников не грузится на каждом заходе. */
export default function WatchPickerModal({
  open, onClose, planId, planIds, watchedIds, quarterStart, quarterEnd,
}: Props) {
  const { message } = App.useApp();
  const { data: employees = [] } = useEmployees({ isActive: true, withTeams: true });
  const { data: roles = [] } = useRoles();
  const add = useAddPlanWatch();
  const [picked, setPicked] = useState<string[]>([]);
  const [team, setTeam] = useState<string | undefined>();
  const [role, setRole] = useState<string | undefined>();

  const inPlan = useMemo(() => new Set(planIds), [planIds]);
  const watched = useMemo(() => new Set(watchedIds), [watchedIds]);
  const excluded = useMemo(() => new Set([...planIds, ...watchedIds]), [planIds, watchedIds]);
  const roleLabel = useMemo(() => new Map(roles.map((r) => [r.code, r.label])), [roles]);
  const options = useMemo(
    () => watchPickerOptions(employees, inPlan, watched, roleLabel),
    [employees, inPlan, watched, roleLabel],
  );
  const teamOptions = useMemo(() => {
    const names = new Set<string>();
    for (const e of employees) {
      for (const t of e.teams ?? []) names.add(t.team);
      if (e.team) names.add(e.team);
    }
    return [...names].sort((a, b) => a.localeCompare(b, 'ru')).map((t) => ({ value: t, label: t }));
  }, [employees]);
  const roleOptions = roles.filter((r) => r.is_active).map((r) => ({ value: r.code, label: r.label }));

  const addRole = () => {
    if (!team || !role) return;
    const ids = roleTeamPicks(employees, team, role, quarterStart, quarterEnd).filter((id) => !excluded.has(id));
    if (ids.length === 0) {
      message.info('В команде нет сотрудников этой роли, которых ещё нет в плане или в списке');
      return;
    }
    setPicked((prev) => Array.from(new Set([...prev, ...ids])));
  };

  const close = () => {
    setPicked([]);
    onClose();
  };

  const submit = async () => {
    try {
      await add.mutateAsync({ planId, employeeIds: picked });
      close();
    } catch {
      message.error('Не удалось добавить людей');
    }
  };

  return (
    <Modal
      open={open}
      title="Подобрать людей"
      okText="Добавить"
      cancelText="Отмена"
      onOk={submit}
      onCancel={close}
      confirmLoading={add.isPending}
      okButtonProps={{ disabled: picked.length === 0 }}
      destroyOnHidden
      width={640}
    >
      <Typography.Paragraph type="secondary" style={{ fontSize: 12 }}>
        Выбранные появятся в «Загрузке по дням» секцией «Наблюдаемые»: загрузка по дням, свободное время по
        месяцам и остаток «Технических задач» основной команды. Список общий для плана — его видят все, кто
        открывает план. Люди этого плана уже есть в «Загрузке по дням» — их выбрать нельзя.
      </Typography.Paragraph>
      <Select
        mode="multiple"
        showSearch
        allowClear
        optionFilterProp="label"
        placeholder="Найдите сотрудника по ФИО"
        aria-label="Сотрудники"
        value={picked}
        onChange={setPicked}
        options={options}
        maxTagCount={8}
        style={{ width: '100%' }}
      />
      <div style={{ display: 'flex', gap: 8, marginTop: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontSize: 12 }}>Вся роль в команде:</span>
        <Select
          showSearch
          placeholder="Команда"
          aria-label="Команда"
          value={team}
          onChange={setTeam}
          options={teamOptions}
          style={{ flex: '1 1 220px' }}
        />
        <Select
          placeholder="Роль"
          aria-label="Роль"
          value={role}
          onChange={setRole}
          options={roleOptions}
          style={{ width: 170 }}
        />
        <Button onClick={addRole} disabled={!team || !role}>
          Добавить всех
        </Button>
      </div>
    </Modal>
  );
}
