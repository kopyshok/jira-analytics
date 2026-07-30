import { useEffect, useState } from 'react';
import { App, Button, Card, Input, InputNumber, Radio, Space, Tag, TimePicker, Typography } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import dayjs, { type Dayjs } from 'dayjs';
import { PlusOutlined } from '@ant-design/icons';
import { fetchGeneral, saveGeneral, type KpiGeneralSettings } from '../../../api/kpi';

const { Text } = Typography;

const EMPTY_POLICY_OPTIONS = [
  { value: 'redistribute', label: 'Не учитывать метрику и перераспределить её вес между остальными' },
  { value: 'full', label: 'Считать метрику выполненной на 100%' },
  { value: 'zero', label: 'Считать метрику невыполненной, 0%' },
];

const WEEKDAY_NAMES_RU = ['понедельника', 'вторника', 'среды', 'четверга', 'пятницы', 'субботы', 'воскресенья'];

/** Иллюстративный пример по будним дням (Пн–Пт), без учёта праздников —
 * точный расчёт с производственным календарём делает бэкенд при подсчёте KPI. */
function overdueExample(days: number, time: string): string {
  const workDay = dayjs('2026-07-24'); // пятница, для наглядности примера
  let cursor = workDay;
  let remaining = Math.max(1, days);
  for (let i = 0; i < 30 && remaining > 0; i += 1) {
    cursor = cursor.add(1, 'day');
    if (cursor.day() !== 0 && cursor.day() !== 6) remaining -= 1;
  }
  const dayName = WEEKDAY_NAMES_RU[cursor.day() === 0 ? 6 : cursor.day() - 1];
  return `Часы за пятницу ${workDay.format('D MMMM')} нужно внести до ${dayName} ${cursor.format('D MMMM')}, ${time}. Праздники здесь не учтены — только пример.`;
}

export default function GeneralRules() {
  const { notification } = App.useApp();
  const qc = useQueryClient();

  const generalQuery = useQuery({ queryKey: ['kpi-settings', 'general'], queryFn: fetchGeneral });
  const [form, setForm] = useState<KpiGeneralSettings | null>(null);
  const [statusInput, setStatusInput] = useState('');

  useEffect(() => {
    if (generalQuery.data && !form) setForm(generalQuery.data);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [generalQuery.data]);

  const saveMut = useMutation({
    mutationFn: (body: KpiGeneralSettings) => saveGeneral(body),
    onSuccess: (data) => {
      qc.setQueryData(['kpi-settings', 'general'], data);
      notification.success({ title: 'Правила сохранены' });
    },
    onError: (e: Error) => notification.error({ title: 'Не удалось сохранить', description: e.message }),
  });

  if (!form) return null;

  const addStatus = () => {
    const v = statusInput.trim();
    if (!v || form.excluded_statuses.includes(v)) return;
    setForm({ ...form, excluded_statuses: [...form.excluded_statuses, v] });
    setStatusInput('');
  };
  const removeStatus = (v: string) => {
    setForm({ ...form, excluded_statuses: form.excluded_statuses.filter((s) => s !== v) });
  };

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <Card size="small" title="Статусы, которые не считаются выполнением">
        <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 10 }}>
          Задачи в этих статусах не попадают в знаменатель ни одной метрики, даже если формально закрыты.
        </Text>
        <Space wrap style={{ marginBottom: 10 }}>
          {form.excluded_statuses.map((s) => (
            <Tag key={s} closable onClose={() => removeStatus(s)}>{s}</Tag>
          ))}
        </Space>
        <Space>
          <Input
            style={{ width: 240 }}
            placeholder="Например: Отклонено, Дубликат"
            value={statusInput}
            onChange={(e) => setStatusInput(e.target.value)}
            onPressEnter={addStatus}
          />
          <Button icon={<PlusOutlined />} onClick={addStatus}>Добавить</Button>
        </Space>
      </Card>

      <Card size="small" title="Срок внесения трудозатрат">
        <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 10 }}>
          Часы за рабочий день должны быть внесены не позже указанного времени следующего рабочего
          дня. Выходные и праздники пропускаются по производственному календарю.
        </Text>
        <Space size="large">
          <div>
            <Text type="secondary" style={{ fontSize: 11 }}>Дать рабочих дней</Text><br />
            <InputNumber
              min={1} max={5} value={form.worklog_deadline_days}
              onChange={(v) => setForm({ ...form, worklog_deadline_days: v ?? 1 })}
            />
          </div>
          <div>
            <Text type="secondary" style={{ fontSize: 11 }}>Не позже</Text><br />
            <TimePicker
              format="HH:mm" value={dayjs(form.worklog_deadline_time, 'HH:mm')}
              onChange={(v: Dayjs | null) => setForm({ ...form, worklog_deadline_time: v ? v.format('HH:mm') : form.worklog_deadline_time })}
              allowClear={false}
            />
          </div>
        </Space>
        <div style={{ marginTop: 10, fontSize: 12, color: 'var(--text-2, inherit)' }}>
          {overdueExample(form.worklog_deadline_days, form.worklog_deadline_time)}
        </div>
      </Card>

      <Card size="small" title="Если данных для расчёта нет">
        <Radio.Group
          value={form.empty_policy}
          onChange={(e) => setForm({ ...form, empty_policy: e.target.value })}
        >
          <Space orientation="vertical">
            {EMPTY_POLICY_OPTIONS.map((o) => (
              <Radio key={o.value} value={o.value}>{o.label}</Radio>
            ))}
          </Space>
        </Radio.Group>
      </Card>

      <Button type="primary" loading={saveMut.isPending} onClick={() => saveMut.mutate(form)}>
        Сохранить общие правила
      </Button>
    </Space>
  );
}
