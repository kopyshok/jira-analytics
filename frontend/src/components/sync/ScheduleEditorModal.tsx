import { useEffect, useMemo, useState } from 'react';
import {
  Alert, Checkbox, Form, Input, Modal, Select, Switch, TimePicker, Typography, App,
} from 'antd';
import dayjs, { type Dayjs } from 'dayjs';
import { useMutation } from '@tanstack/react-query';
import {
  createSchedule, updateSchedule, previewSchedule,
  type SchedulePreviewResponse, type SyncScheduleOut, type SyncScheduleCreate,
  type SyncScheduleUpdate,
} from '../../api/syncSchedule';
import type { PipelineMode } from '../../api/syncRuns';
import {
  type ScheduleType, type ScheduleForm,
  parseCron, buildCron, MINUTE_OPTIONS, HOUR_OPTIONS, DAY_OPTIONS,
} from '../../utils/cronBuilder';

const MODE_LABELS: Record<PipelineMode, string> = {
  quick: 'Быстрый',
  normal: 'Обычный',
  full: 'Полный',
  team: 'По команде',
};

const TYPE_OPTIONS: { value: ScheduleType; label: string }[] = [
  { value: 'every_minutes', label: 'Каждые N минут' },
  { value: 'every_hours', label: 'Каждые N часов' },
  { value: 'daily', label: 'Каждый день в...' },
  { value: 'weekdays', label: 'Будни (пн-пт) в...' },
  { value: 'weekends', label: 'Выходные (сб-вс) в...' },
  { value: 'specific_days', label: 'По дням недели в...' },
  { value: 'weekly', label: 'Еженедельно в...' },
  { value: 'cron', label: 'Произвольно (cron-выражение)' },
];

interface FormValues {
  name: string;
  type: ScheduleType;
  minutes?: number;
  hours?: number;
  time?: Dayjs;
  days?: number[];
  day?: number;
  cron?: string;
  mode: PipelineMode;
  team?: string | null;
  enabled: boolean;
}

function valuesToScheduleForm(v: FormValues): ScheduleForm {
  return {
    type: v.type,
    minutes: v.minutes,
    hours: v.hours,
    time: v.time ? v.time.format('HH:mm') : undefined,
    days: v.days,
    day: v.day,
    cron: v.cron,
  };
}

function scheduleFormToValues(
  f: ScheduleForm,
  base: Partial<FormValues>,
): FormValues {
  return {
    name: base.name ?? '',
    type: f.type,
    minutes: f.minutes ?? 5,
    hours: f.hours ?? 2,
    time: f.time ? dayjs(f.time, 'HH:mm') : dayjs('06:00', 'HH:mm'),
    days: f.days ?? [0, 3],
    day: f.day ?? 0,
    cron: f.cron ?? '0 6 * * *',
    mode: (base.mode as PipelineMode) ?? 'normal',
    team: base.team,
    enabled: base.enabled ?? true,
  };
}

interface Props {
  open: boolean;
  schedule: SyncScheduleOut | null;
  onClose: () => void;
  onSaved: () => void;
}

export default function ScheduleEditorModal({ open, schedule, onClose, onSaved }: Props) {
  const isEdit = schedule !== null;
  const { notification } = App.useApp();
  const [form] = Form.useForm<FormValues>();
  const [preview, setPreview] = useState<SchedulePreviewResponse | null>(null);

  const initialValues = useMemo<FormValues>(() => {
    const initialForm: ScheduleForm = schedule
      ? parseCron(schedule.cron_expr)
      : { type: 'daily', time: '06:00' };
    return scheduleFormToValues(initialForm, {
      name: schedule?.name ?? '',
      mode: (schedule?.mode as PipelineMode | undefined) ?? 'normal',
      team: schedule?.team ?? undefined,
      enabled: schedule?.enabled ?? true,
    });
    // schedule identity достаточно — open + destroyOnHidden пересоздаёт modal
  }, [schedule]);

  const watched = Form.useWatch([], form);

  const currentCron = useMemo(() => {
    const v = (watched ?? initialValues) as FormValues;
    return buildCron(valuesToScheduleForm(v));
  }, [watched, initialValues]);

  const type: ScheduleType = (watched?.type ?? initialValues.type) as ScheduleType;
  const mode: PipelineMode = (watched?.mode ?? initialValues.mode) as PipelineMode;

  useEffect(() => {
    if (!currentCron) return undefined;
    let cancelled = false;
    const t = setTimeout(() => {
      previewSchedule(currentCron)
        .then((p) => { if (!cancelled) setPreview(p); })
        .catch(() => { if (!cancelled) setPreview(null); });
    }, 300);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [currentCron]);

  const createMut = useMutation({
    mutationFn: (body: SyncScheduleCreate) => createSchedule(body),
    onSuccess: () => { onSaved(); onClose(); },
    onError: (e) =>
      notification.error({ title: 'Ошибка создания', description: (e as Error).message }),
  });

  const updateMut = useMutation({
    mutationFn: (body: SyncScheduleUpdate) =>
      updateSchedule(schedule!.id, body),
    onSuccess: () => { onSaved(); onClose(); },
    onError: (e) =>
      notification.error({ title: 'Ошибка сохранения', description: (e as Error).message }),
  });

  const handleOk = async () => {
    const v = await form.validateFields();
    const cron = buildCron(valuesToScheduleForm(v));
    if (isEdit) {
      const body: SyncScheduleUpdate = {
        cron_expr: cron,
        mode: v.mode,
        team: v.mode === 'team' ? (v.team ?? null) : null,
        enabled: v.enabled,
      };
      updateMut.mutate(body);
    } else {
      const body: SyncScheduleCreate = {
        name: v.name,
        cron_expr: cron,
        mode: v.mode,
        team: v.mode === 'team' ? (v.team ?? undefined) : undefined,
        enabled: v.enabled,
      };
      createMut.mutate(body);
    }
  };

  const previewBlock = useMemo(() => {
    if (!preview) return null;
    if (!preview.valid) {
      return (
        <Alert
          type="error"
          showIcon
          title={preview.error ?? 'Невалидное расписание'}
        />
      );
    }
    const runs = preview.next_runs
      .map((iso) => dayjs(iso).format('DD.MM.YYYY HH:mm'))
      .join(', ');
    return (
      <Alert
        type="info"
        showIcon
        title={preview.description}
        description={`Следующие запуски: ${runs}`}
      />
    );
  }, [preview]);

  return (
    <Modal
      title={isEdit ? 'Редактирование расписания' : 'Новое расписание'}
      open={open}
      onCancel={onClose}
      onOk={handleOk}
      confirmLoading={createMut.isPending || updateMut.isPending}
      okText="Сохранить"
      cancelText="Отмена"
      width={580}
      destroyOnHidden
    >
      <Form<FormValues>
        form={form}
        layout="vertical"
        initialValues={initialValues}
        preserve={false}
      >
        <Form.Item
          name="name"
          label="Название"
          rules={[{ required: true, message: 'Укажите название' }]}
        >
          <Input placeholder="Например, утренний полный синк" />
        </Form.Item>

        <Form.Item
          name="type"
          label="Тип расписания"
          rules={[{ required: true }]}
        >
          <Select options={TYPE_OPTIONS} />
        </Form.Item>

        {type === 'every_minutes' && (
          <Form.Item
            name="minutes"
            label="Каждые ... минут"
            rules={[{ required: true }]}
            extra="Доступны делители 60: 1, 2, 3, 4, 5, 6, 10, 12, 15, 20, 30"
          >
            <Select
              options={MINUTE_OPTIONS.map((n) => ({ value: n, label: `${n} мин` }))}
              style={{ width: 200 }}
            />
          </Form.Item>
        )}

        {type === 'every_hours' && (
          <Form.Item
            name="hours"
            label="Каждые ... часов"
            rules={[{ required: true }]}
            extra="Доступны делители 24: 1, 2, 3, 4, 6, 8, 12"
          >
            <Select
              options={HOUR_OPTIONS.map((n) => ({ value: n, label: `${n} ч` }))}
              style={{ width: 200 }}
            />
          </Form.Item>
        )}

        {(type === 'daily' || type === 'weekdays' || type === 'weekends'
          || type === 'specific_days' || type === 'weekly') && (
          <Form.Item
            name="time"
            label="Время"
            rules={[{ required: true, message: 'Укажите время' }]}
          >
            <TimePicker format="HH:mm" minuteStep={5} style={{ width: 160 }} />
          </Form.Item>
        )}

        {type === 'specific_days' && (
          <Form.Item
            name="days"
            label="Дни недели"
            rules={[
              {
                validator: (_, v) =>
                  v && v.length > 0
                    ? Promise.resolve()
                    : Promise.reject(new Error('Выберите хотя бы один день')),
              },
            ]}
          >
            <Checkbox.Group options={DAY_OPTIONS} />
          </Form.Item>
        )}

        {type === 'weekly' && (
          <Form.Item
            name="day"
            label="День недели"
            rules={[{ required: true }]}
          >
            <Select options={DAY_OPTIONS} style={{ width: 200 }} />
          </Form.Item>
        )}

        {type === 'cron' && (
          <Form.Item
            name="cron"
            label="Cron-выражение"
            rules={[{ required: true, message: 'Введите cron-выражение' }]}
            extra="Стандартный формат: минута час день месяц день_недели"
          >
            <Input placeholder="0 6 * * *" />
          </Form.Item>
        )}

        <Form.Item
          name="mode"
          label="Режим запуска"
          rules={[{ required: true }]}
        >
          <Select
            options={(Object.entries(MODE_LABELS) as [PipelineMode, string][]).map(
              ([value, label]) => ({ value, label }),
            )}
          />
        </Form.Item>

        {mode === 'team' && (
          <Form.Item
            name="team"
            label="Команда"
            rules={[{ required: true, message: 'Укажите название команды' }]}
          >
            <Input placeholder="Название команды" />
          </Form.Item>
        )}

        <Form.Item name="enabled" label="Включено" valuePropName="checked">
          <Switch />
        </Form.Item>

        {previewBlock && <div style={{ marginTop: 8 }}>{previewBlock}</div>}

        {currentCron && (
          <Typography.Text
            type="secondary"
            style={{ fontSize: 11, display: 'block', marginTop: 8 }}
          >
            Cron: <code>{currentCron}</code>
          </Typography.Text>
        )}
      </Form>
    </Modal>
  );
}
