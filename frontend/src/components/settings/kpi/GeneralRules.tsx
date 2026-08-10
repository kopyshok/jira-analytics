import { useEffect, useState } from 'react';
import {
  App, Alert, Button, Card, DatePicker, Input, InputNumber, Radio, Select, Space, Switch, Table,
  Tag, TimePicker, Typography,
} from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import dayjs, { type Dayjs } from 'dayjs';
import { PlusOutlined } from '@ant-design/icons';
import {
  fetchDeadlineCompare, fetchGeneral, saveGeneral,
  type KpiDeadlineCompareRow, type KpiGeneralSettings,
} from '../../../api/kpi';
import { useGlobalTeamFilter } from '../../../hooks/useGlobalTeamFilter';
import { useTeams } from '../../../hooks/useSync';
import { useThemeTokens } from '../../../aurora/theme/useThemeTokens';

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

/** Пример для способа по ТЗ: календарь не участвует, поэтому счёт прямой. */
function hoursExample(hours: number): string {
  const started = dayjs('2026-07-24T09:00'); // пятница, 9 утра
  const deadline = started.add(hours, 'hour');
  return `Работа начата в пятницу ${started.format('D MMMM')} в 09:00 — внести до `
    + `${deadline.format('D MMMM, HH:mm')}. Выходные не пропускаются.`;
}

/**
 * Сравнение способов на живых данных: способ по ТЗ строже, потому что не
 * прощает выходные. Переключать вслепую нельзя — сначала видно, как он ляжет
 * на людей.
 */
function DeadlineComparison() {
  const t = useThemeTokens();
  const { selectedTeams } = useGlobalTeamFilter();
  const now = new Date();
  const [team, setTeam] = useState<string | undefined>(selectedTeams[0]);
  const [period, setPeriod] = useState<Dayjs>(dayjs(new Date(now.getFullYear(), now.getMonth() - 1, 1)));
  const [enabled, setEnabled] = useState(false);

  const teamsQuery = useTeams();
  const compareQuery = useQuery({
    queryKey: ['kpi-settings', 'deadline-compare', team, period.year(), period.month() + 1],
    queryFn: () => fetchDeadlineCompare(team as string, period.year(), period.month() + 1),
    enabled: enabled && !!team,
  });

  const pct = (v: number | null) => (v == null ? '—' : `${Math.round(v)}%`);

  return (
    <Card size="small" title="Сравнить способы на данных">
      <Space wrap align="end" style={{ marginBottom: 12 }}>
        <div>
          <Text type="secondary" style={{ fontSize: 11 }}>Команда</Text><br />
          <Select
            style={{ minWidth: 260 }} value={team} onChange={setTeam}
            placeholder="Выберите команду"
            options={(teamsQuery.data ?? []).map((x) => ({ value: x, label: x }))}
          />
        </div>
        <div>
          <Text type="secondary" style={{ fontSize: 11 }}>Месяц</Text><br />
          <DatePicker
            picker="month" value={period} allowClear={false}
            onChange={(v: Dayjs | null) => v && setPeriod(v)}
          />
        </div>
        <Button
          onClick={() => { setEnabled(true); compareQuery.refetch(); }}
          loading={compareQuery.isFetching} disabled={!team}
        >
          Сравнить
        </Button>
      </Space>

      {compareQuery.data && (
        <Table
          dataSource={compareQuery.data.rows}
          rowKey="employee_name"
          size="small"
          pagination={false}
          columns={[
            { title: 'Сотрудник', dataIndex: 'employee_name' },
            { title: 'Записей', dataIndex: 'worklog_count', width: 100, align: 'right' },
            {
              title: 'Часов от времени работы', width: 200, align: 'right',
              render: (_: unknown, r: KpiDeadlineCompareRow) => (
                <span className="num">{pct(r.hours_from_start)}</span>
              ),
            },
            {
              title: 'Рабочие дни + отсечка', width: 190, align: 'right',
              render: (_: unknown, r: KpiDeadlineCompareRow) => (
                <span className="num">{pct(r.calendar)}</span>
              ),
            },
            {
              title: 'Разница', width: 110, align: 'right',
              render: (_: unknown, r: KpiDeadlineCompareRow) => {
                if (r.hours_from_start == null || r.calendar == null) return '—';
                const delta = Math.round(r.hours_from_start - r.calendar);
                return (
                  <span className="num" style={{ color: delta < 0 ? t.danger : t.textMuted }}>
                    {delta > 0 ? `+${delta}` : delta}
                  </span>
                );
              },
            },
          ]}
        />
      )}
      {compareQuery.data?.rows.length === 0 && (
        <Text type="secondary" style={{ fontSize: 12 }}>
          За этот месяц по команде нет записей о трудозатратах.
        </Text>
      )}
    </Card>
  );
}

export default function GeneralRules() {
  const { notification } = App.useApp();
  const qc = useQueryClient();
  const t = useThemeTokens();

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
      // Исключённые статусы, срок внесения часов и политика пустых данных
      // участвуют в живом расчёте — ведомость должна пересчитаться (см.
      // ревью, ВАЖНО 7).
      qc.invalidateQueries({ queryKey: ['kpi'] });
      notification.success({ title: 'Правила сохранены' });
    },
    onError: (e: Error) => notification.error({ title: 'Не удалось сохранить', description: e.message }),
  });

  if (!form) {
    // Раньше на ошибке запроса блок общих правил просто исчезал (форма
    // никогда не гидрировалась) — руководитель не видел ни правил, ни
    // причины, почему их нет (см. ревью, ВАЖНО 6).
    if (generalQuery.isError) {
      return (
        <Alert
          type="error"
          showIcon
          title="Не удалось загрузить общие правила"
          description={(generalQuery.error as Error).message}
          action={<Button size="small" onClick={() => generalQuery.refetch()}>Повторить</Button>}
        />
      );
    }
    return null;
  }

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
        <Radio.Group
          value={form.worklog_deadline_mode}
          onChange={(e) => setForm({ ...form, worklog_deadline_mode: e.target.value })}
          style={{ width: '100%' }}
        >
          <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
            <div>
              <Radio value="hours_from_start">
                Часов от времени работы <Text type="secondary" style={{ fontSize: 11.5 }}>· как в ТЗ</Text>
              </Radio>
              <div style={{ paddingLeft: 24, marginTop: 4 }}>
                <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>
                  Запись просрочена, если создана позже чем через указанное число часов после
                  времени начала работы, записанного в ней. Производственный календарь не
                  участвует — счёт непрерывный, выходные не прощаются.
                </Text>
                <Text type="secondary" style={{ fontSize: 11 }}>Часов на внесение</Text><br />
                <InputNumber
                  min={1} max={168} value={form.worklog_deadline_hours}
                  disabled={form.worklog_deadline_mode !== 'hours_from_start'}
                  onChange={(v) => setForm({ ...form, worklog_deadline_hours: v ?? 18 })}
                />
                <div style={{ marginTop: 8, fontSize: 12, color: t.textMuted }}>
                  {hoursExample(form.worklog_deadline_hours)}
                </div>
              </div>
            </div>

            <div>
              <Radio value="calendar">Рабочие дни и время отсечки</Radio>
              <div style={{ paddingLeft: 24, marginTop: 4 }}>
                <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>
                  Часы за рабочий день внесены вовремя, если запись создана не позже указанного
                  времени N-го рабочего дня. Выходные и праздники пропускаются по
                  производственному календарю.
                </Text>
                <Space size="large">
                  <div>
                    <Text type="secondary" style={{ fontSize: 11 }}>Дать рабочих дней</Text><br />
                    <InputNumber
                      min={1} max={5} value={form.worklog_deadline_days}
                      disabled={form.worklog_deadline_mode !== 'calendar'}
                      onChange={(v) => setForm({ ...form, worklog_deadline_days: v ?? 1 })}
                    />
                  </div>
                  <div>
                    <Text type="secondary" style={{ fontSize: 11 }}>Не позже</Text><br />
                    <TimePicker
                      format="HH:mm" value={dayjs(form.worklog_deadline_time, 'HH:mm')}
                      disabled={form.worklog_deadline_mode !== 'calendar'}
                      onChange={(v: Dayjs | null) => setForm({ ...form, worklog_deadline_time: v ? v.format('HH:mm') : form.worklog_deadline_time })}
                      allowClear={false}
                    />
                  </div>
                </Space>
                <div style={{ marginTop: 8, fontSize: 12, color: t.textMuted }}>
                  {overdueExample(form.worklog_deadline_days, form.worklog_deadline_time)}
                </div>
              </div>
            </div>
          </Space>
        </Radio.Group>
      </Card>

      <DeadlineComparison />

      <Card size="small" title="Если данных для расчёта нет">
        <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 10 }}>
          Правило по умолчанию для всех метрик. У отдельной метрики можно задать своё —
          в конструкторе метрики, блок «Если данных для расчёта нет».
        </Text>
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

      <Card size="small" title="Утверждение квартала">
        <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 10 }}>
          Утверждение замораживает результат квартала снимком: правки весов профиля и нормативов
          после этого на подписанный квартал не влияют. Пока раздел обкатывают, утверждение можно
          не включать — кнопка не появится в ведомости, а попытка утвердить будет отклонена.
        </Text>
        <Switch
          checked={form.approval_enabled}
          onChange={(checked) => setForm({ ...form, approval_enabled: checked })}
        />
        <Text style={{ marginLeft: 10, fontSize: 13 }}>
          {form.approval_enabled ? 'Включено' : 'Выключено'}
        </Text>
      </Card>

      <Button type="primary" loading={saveMut.isPending} onClick={() => saveMut.mutate(form)}>
        Сохранить общие правила
      </Button>
    </Space>
  );
}
