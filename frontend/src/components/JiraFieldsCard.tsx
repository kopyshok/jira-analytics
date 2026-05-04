import { useEffect, useState } from 'react';
import { Card, Form, Select, Button, Space, App, Collapse, Typography } from 'antd';
import { SaveOutlined } from '@ant-design/icons';
import { useGenericSetting, useSaveGenericSetting } from '../hooks/useSettings';
import { useJiraFields } from '../hooks/useSync';

const { Text } = Typography;

interface FieldDef {
  key: string;
  label: string;
}

interface FieldGroup {
  panelKey: string;
  title: string;
  subtitle?: string;
  fields: FieldDef[];
}

const GROUPS: FieldGroup[] = [
  {
    panelKey: 'core',
    title: 'Команды и цели',
    fields: [
      { key: 'jira_team_field_id', label: 'Поле продуктовой команды' },
      { key: 'jira_participating_teams_field_id', label: 'Поле участвующих команд' },
      { key: 'jira_goals_field_id', label: 'Поле целей' },
    ],
  },
  {
    panelKey: 'description_extra',
    title: 'Описание задачи (для AI-саммари)',
    subtitle: 'Кастомные поля с целями и текущим поведением — попадают в промпт LLM',
    fields: [
      { key: 'jira_goal_field_id', label: 'Цель задачи' },
      { key: 'jira_current_behavior_field_id', label: 'Текущее поведение' },
    ],
  },
  {
    panelKey: 'planned_hours',
    title: 'Плановые трудозатраты (часы)',
    fields: [
      { key: 'jira_planned_analyst_hours_field_id', label: 'Анализ (часы)' },
      { key: 'jira_planned_dev_hours_field_id',     label: 'Разработка (часы)' },
      { key: 'jira_planned_qa_hours_field_id',      label: 'Тестирование (часы)' },
      { key: 'jira_planned_opo_hours_field_id',     label: 'ОПЭ (часы)' },
    ],
  },
  {
    panelKey: 'involvement_duration',
    title: 'Вовлеченность и длительности',
    subtitle: 'Для будущего календарного планирования',
    fields: [
      { key: 'jira_involvement_analyst_field_id', label: 'Вовлеченность аналитика' },
      { key: 'jira_involvement_dev_field_id',     label: 'Вовлеченность разработчика' },
      { key: 'jira_involvement_qa_field_id',      label: 'Вовлеченность тестировщика' },
      { key: 'jira_involvement_opo_field_id',     label: 'Вовлеченность ОПЭ' },
      { key: 'jira_duration_analyst_field_id',    label: 'Длительность анализа' },
      { key: 'jira_duration_dev_field_id',        label: 'Длительность разработки' },
      { key: 'jira_duration_qa_field_id',         label: 'Длительность тестирования' },
      { key: 'jira_duration_opo_field_id',        label: 'Длительность ОПЭ' },
    ],
  },
  {
    panelKey: 'prioritization',
    title: 'Приоритизация',
    fields: [
      { key: 'jira_impact_field_id', label: 'Impact' },
      { key: 'jira_risk_field_id',   label: 'Risk' },
    ],
  },
  {
    panelKey: 'customer_rating',
    title: 'Оценка заказчика',
    subtitle: 'Шкала 1–5 по трём направлениям',
    fields: [
      { key: 'jira_rating_quality_field_id', label: 'Качество' },
      { key: 'jira_rating_speed_field_id',   label: 'Скорость' },
      { key: 'jira_rating_result_field_id',  label: 'Результат' },
    ],
  },
  {
    panelKey: 'planned_dates',
    title: 'Плановые даты',
    subtitle: 'Зарезервированы под будущий инструмент планирования',
    fields: [
      { key: 'jira_planned_start_date_field_id', label: 'Дата начала' },
      { key: 'jira_planned_end_date_field_id',   label: 'Дата окончания' },
    ],
  },
];

const ALL_FIELDS: FieldDef[] = GROUPS.flatMap(g => g.fields);

export default function JiraFieldsCard() {
  const { message } = App.useApp();
  const save = useSaveGenericSetting();
  const jiraFields = useJiraFields();

  // Load each setting. Hooks are called in a stable order from ALL_FIELDS.
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const settings = ALL_FIELDS.map(f => ({ ...f, hook: useGenericSetting(f.key) }));
  const [values, setValues] = useState<Record<string, string>>({});
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (loaded) return;
    if (settings.every(s => s.hook.data !== undefined)) {
      const next: Record<string, string> = {};
      settings.forEach(s => { next[s.key] = s.hook.data?.value ?? ''; });
      setValues(next);
      setLoaded(true);
    }
  }, [loaded, settings]);

  const fieldOptions = (jiraFields.data ?? []).map(f => ({
    value: f.id,
    label: `${f.name} (${f.id})`,
  }));

  const handleSaveAll = () => {
    Promise.all(ALL_FIELDS.map(f =>
      save.mutateAsync({ key: f.key, value: values[f.key] ?? '' })
    )).then(() => message.success('Сохранено'))
      .catch(e => message.error(e.message));
  };

  const renderField = (f: FieldDef) => (
    <Form.Item key={f.key} label={f.label} style={{ marginBottom: 8 }}>
      <Select
        value={values[f.key] || undefined}
        onChange={v => setValues(prev => ({ ...prev, [f.key]: v || '' }))}
        showSearch
        allowClear
        optionFilterProp="label"
        placeholder={`customfield_XXXXX`}
        options={fieldOptions}
        loading={jiraFields.isFetching}
        onDropdownVisibleChange={open => {
          if (open && !jiraFields.data) jiraFields.refetch();
        }}
      />
    </Form.Item>
  );

  return (
    <Card
      title="Кастомные поля Jira"
      size="small"
      extra={
        <Button
          size="small"
          icon={<SaveOutlined />}
          onClick={handleSaveAll}
          loading={save.isPending}
        >
          Сохранить
        </Button>
      }
    >
      <Form layout="vertical">
        <Collapse
          defaultActiveKey={['core', 'description_extra', 'planned_hours', 'prioritization', 'customer_rating']}
          items={GROUPS.map(g => ({
            key: g.panelKey,
            label: g.title,
            children: (
              <Space direction="vertical" style={{ width: '100%' }}>
                {g.subtitle && <Text type="secondary" style={{ fontSize: 12 }}>{g.subtitle}</Text>}
                {g.fields.map(renderField)}
              </Space>
            ),
          }))}
        />
      </Form>
    </Card>
  );
}
