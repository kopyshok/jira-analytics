import { useEffect, useMemo, useState } from 'react';
import {
  App, Button, Card, Input, InputNumber, Popconfirm, Select, Space, Switch, Typography,
} from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import MetricPreview from './MetricPreview';
import { useThemeTokens } from '../../../aurora/theme/useThemeTokens';
import {
  createMetric, deleteMetric, fetchAttributes, fetchMetrics, updateMetric,
  type KpiCondition, type KpiConditionSet, type KpiMetricDef, type KpiMetricPayload,
} from '../../../api/kpi';

const { Text, Title } = Typography;

const CALC_KIND_OPTIONS = [
  { value: 'ratio', label: 'Доля' },
  { value: 'norm_to_fact', label: 'Норматив к факту' },
  { value: 'score_to_max', label: 'Средний балл к максимуму' },
];

const UNIT_OPTIONS = [
  { value: 'issues', label: 'Задачи' },
  { value: 'worklogs', label: 'Записи о трудозатратах' },
];

const PERSON_FIELD_LABELS: Record<string, string> = {
  author: 'Автор задачи',
  assignee: 'Исполнитель задачи',
  linked_issue_author: 'Автор связанной задачи',
  worklog_author: 'Автор записи о трудозатратах',
};

const PERIOD_WINDOW_LABELS: Record<string, string> = {
  closed_in: 'Закрыта в периоде',
  created_and_closed_in: 'Создана и закрыта в периоде',
  open_or_closed_in: 'Закрыта в периоде или открыта на его конец',
};

const LIST_OPS = [
  { value: 'in', label: 'входит в список' },
  { value: 'not_in', label: 'не входит в список' },
  { value: 'eq', label: 'равно' },
  { value: 'ne', label: 'не равно' },
];

const EMPTY_CONDITION_SET: KpiConditionSet = {
  unit: 'issues', person_field: 'author', period_window: 'closed_in', conditions: [],
};

function blankMetricForm(sortOrder = 0): KpiMetricPayload {
  return {
    code: '', name: '', description: '', calc_kind: 'ratio',
    numerator: { ...EMPTY_CONDITION_SET }, denominator: { ...EMPTY_CONDITION_SET },
    fact_field: null, score_fields: null, score_max: 5, invert: false, cap_at_100: true,
    sort_order: sortOrder,
  };
}

function formulaText(f: KpiMetricPayload): string {
  if (f.calc_kind === 'norm_to_fact') return 'Норматив / Средний фактический показатель × 100, потолок 100%';
  if (f.calc_kind === 'score_to_max') return `Средний балл / ${f.score_max ?? 5} × 100`;
  return f.invert ? '100 − Числитель / Знаменатель × 100' : 'Числитель / Знаменатель × 100';
}

interface ConditionSetEditorProps {
  title: string;
  value: KpiConditionSet;
  onChange: (next: KpiConditionSet) => void;
  attributes: ReturnType<typeof fetchAttributes> extends Promise<infer R>
    ? R extends { attributes: (infer A)[] } ? A[] : never : never;
  personFields: string[];
  periodWindows: string[];
}

function ConditionSetEditor({
  title, value, onChange, attributes, personFields, periodWindows,
}: ConditionSetEditorProps) {
  const attrByKey = useMemo(() => new Map(attributes.map((a) => [a.key, a])), [attributes]);

  const updateCondition = (idx: number, patch: Partial<KpiCondition>) => {
    const next = value.conditions.slice();
    next[idx] = { ...next[idx], ...patch };
    onChange({ ...value, conditions: next });
  };
  const removeCondition = (idx: number) => {
    onChange({ ...value, conditions: value.conditions.filter((_, i) => i !== idx) });
  };
  const addCondition = () => {
    const firstAttr = attributes[0]?.key ?? 'project_key';
    onChange({ ...value, conditions: [...value.conditions, { attr: firstAttr, op: 'in', value: [] }] });
  };

  return (
    <Card size="small" title={title} style={{ marginTop: 12 }}>
      <Space wrap style={{ marginBottom: 10 }}>
        <div>
          <Text type="secondary" style={{ fontSize: 11 }}>Единица счёта</Text><br />
          <Select
            size="small" style={{ width: 200 }} options={UNIT_OPTIONS}
            value={value.unit} onChange={(v) => onChange({ ...value, unit: v })}
          />
        </div>
        <div>
          <Text type="secondary" style={{ fontSize: 11 }}>Кто считается</Text><br />
          <Select
            size="small" style={{ width: 220 }}
            options={personFields.map((p) => ({ value: p, label: PERSON_FIELD_LABELS[p] ?? p }))}
            value={value.person_field} onChange={(v) => onChange({ ...value, person_field: v })}
          />
        </div>
        <div>
          <Text type="secondary" style={{ fontSize: 11 }}>Окно периода</Text><br />
          <Select
            size="small" style={{ width: 220 }}
            options={periodWindows.map((p) => ({ value: p, label: PERIOD_WINDOW_LABELS[p] ?? p }))}
            value={value.period_window} onChange={(v) => onChange({ ...value, period_window: v })}
          />
        </div>
      </Space>

      {value.conditions.map((cond, idx) => {
        const def = attrByKey.get(cond.attr);
        const isNone = def?.value_type === 'none';
        const isFieldFilled = cond.attr === 'field_filled';
        return (
          <div key={idx} style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
            <Select
              size="small" style={{ width: 200 }}
              options={attributes.map((a) => ({ value: a.key, label: a.label }))}
              value={cond.attr}
              onChange={(v) => {
                const nd = attrByKey.get(v);
                updateCondition(idx, {
                  attr: v,
                  op: nd?.value_type === 'none' ? 'is_true' : isFieldFilled || v === 'field_filled' ? 'all' : 'in',
                  value: nd?.value_type === 'none' ? null : [],
                });
              }}
            />
            {!isNone && (
              <Select
                size="small" style={{ width: 170 }}
                disabled={isFieldFilled}
                options={isFieldFilled ? [{ value: 'all', label: 'все поля заполнены' }] : LIST_OPS}
                value={cond.op}
                onChange={(v) => updateCondition(idx, { op: v })}
              />
            )}
            {!isNone && (
              <Select
                size="small" mode="tags" style={{ minWidth: 220, flex: 1 }}
                placeholder="Значение"
                options={(def?.choices ?? []).map((c) => ({ value: c, label: c }))}
                value={Array.isArray(cond.value) ? (cond.value as string[]) : cond.value ? [String(cond.value)] : []}
                onChange={(v) => updateCondition(idx, { value: v })}
              />
            )}
            {isNone && <Text type="secondary" style={{ fontSize: 12 }}>{def?.label}</Text>}
            <Button size="small" icon={<DeleteOutlined />} onClick={() => removeCondition(idx)} />
          </div>
        );
      })}
      <Button size="small" icon={<PlusOutlined />} onClick={addCondition}>Добавить условие</Button>
    </Card>
  );
}

export default function MetricEditor() {
  const { notification } = App.useApp();
  const qc = useQueryClient();
  const t = useThemeTokens();

  const metricsQuery = useQuery({ queryKey: ['kpi-settings', 'metrics'], queryFn: fetchMetrics });
  const attributesQuery = useQuery({ queryKey: ['kpi-settings', 'attributes'], queryFn: fetchAttributes });

  const [selectedId, setSelectedId] = useState<string | 'new' | null>(null);
  const [form, setForm] = useState<KpiMetricPayload>(blankMetricForm());

  useEffect(() => {
    if (selectedId === 'new' || selectedId === null) return;
    const m = metricsQuery.data?.find((x) => x.id === selectedId);
    if (m) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- гидратация формы из выбранной метрики
      setForm({
        code: m.code, name: m.name, description: m.description, calc_kind: m.calc_kind,
        numerator: m.numerator, denominator: m.denominator, fact_field: m.fact_field,
        score_fields: m.score_fields, score_max: m.score_max, invert: m.invert,
        cap_at_100: m.cap_at_100, sort_order: m.sort_order,
      });
    }
  }, [selectedId, metricsQuery.data]);

  // Новая метрика встаёт в конец порядка колонок, а не всегда нулевым
  // порядком — иначе порядок колонок для новых метрик был неуправляем
  // (см. ревью, мелочи).
  const startNew = () => {
    const maxOrder = Math.max(0, ...(metricsQuery.data ?? []).map((m) => m.sort_order));
    setSelectedId('new');
    setForm(blankMetricForm(maxOrder + 1));
  };

  // Правка метрики (условия отбора, способ расчёта) меняет живой расчёт
  // ведомости — она должна пересчитаться (см. ревью, ВАЖНО 7).
  const createMut = useMutation({
    mutationFn: (body: KpiMetricPayload) => createMetric(body),
    onSuccess: (m: KpiMetricDef) => {
      qc.invalidateQueries({ queryKey: ['kpi-settings', 'metrics'] });
      qc.invalidateQueries({ queryKey: ['kpi'] });
      notification.success({ title: 'Метрика создана' });
      setSelectedId(m.id);
    },
    onError: (e: Error) => notification.error({ title: 'Не удалось сохранить', description: e.message }),
  });
  const updateMut = useMutation({
    mutationFn: (body: KpiMetricPayload) => updateMetric(selectedId as string, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['kpi-settings', 'metrics'] });
      qc.invalidateQueries({ queryKey: ['kpi'] });
      notification.success({ title: 'Метрика сохранена' });
    },
    onError: (e: Error) => notification.error({ title: 'Не удалось сохранить', description: e.message }),
  });
  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteMetric(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['kpi-settings', 'metrics'] });
      qc.invalidateQueries({ queryKey: ['kpi'] });
      notification.success({ title: 'Метрика удалена' });
      setSelectedId(null);
    },
    onError: (e: Error) => notification.error({ title: 'Не удалось удалить', description: e.message }),
  });

  const save = () => {
    const body: KpiMetricPayload = {
      ...form,
      denominator: form.calc_kind === 'ratio' ? form.denominator : null,
    };
    if (selectedId === 'new') createMut.mutate(body);
    else if (selectedId) updateMut.mutate(body);
  };

  const attributes = attributesQuery.data?.attributes ?? [];
  const personFields = attributesQuery.data?.person_fields ?? [];
  const periodWindows = attributesQuery.data?.period_windows ?? [];
  const factFields = attributesQuery.data?.fact_fields ?? [];
  const selectedIsBuiltin = selectedId !== 'new' && selectedId != null
    && !!metricsQuery.data?.find((m) => m.id === selectedId)?.is_builtin;

  return (
    <div className="constructor-grid-2" style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: 18, alignItems: 'start' }}>
      <div style={{ minWidth: 0 }}>
        <Space wrap style={{ marginBottom: 12 }}>
          <Select
            style={{ width: 280 }}
            placeholder="Выберите метрику"
            loading={metricsQuery.isLoading}
            value={selectedId === 'new' ? undefined : (selectedId ?? undefined)}
            options={(metricsQuery.data ?? []).map((m) => ({ value: m.id, label: m.name }))}
            onChange={setSelectedId}
          />
          <Button icon={<PlusOutlined />} onClick={startNew}>Новая метрика</Button>
          {selectedId && selectedId !== 'new' && (
            <Popconfirm
              title="Удалить метрику? Действие необратимо."
              onConfirm={() => deleteMut.mutate(selectedId)}
              okText="Удалить" cancelText="Отмена"
            >
              <Button danger icon={<DeleteOutlined />} loading={deleteMut.isPending}>Удалить</Button>
            </Popconfirm>
          )}
        </Space>

        {selectedId == null ? (
          <Text type="secondary">Выберите метрику слева или создайте новую.</Text>
        ) : (
          <>
            <Card size="small" title="Основное">
              <Space orientation="vertical" style={{ width: '100%' }} size="small">
                <div>
                  <Text type="secondary" style={{ fontSize: 11 }}>Код (латиницей, уникальный)</Text>
                  <Input
                    value={form.code}
                    disabled={selectedIsBuiltin}
                    onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))}
                  />
                </div>
                <div>
                  <Text type="secondary" style={{ fontSize: 11 }}>Название метрики</Text>
                  <Input value={form.name} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} />
                </div>
                <div>
                  <Text type="secondary" style={{ fontSize: 11 }}>Пояснение для пользователя</Text>
                  <Input.TextArea
                    rows={2} value={form.description ?? ''}
                    onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                  />
                </div>
                <div>
                  <Text type="secondary" style={{ fontSize: 11 }}>Способ расчёта</Text><br />
                  <Select
                    style={{ width: 260 }} options={CALC_KIND_OPTIONS}
                    value={form.calc_kind} onChange={(v) => setForm((f) => ({ ...f, calc_kind: v }))}
                  />
                </div>
              </Space>
            </Card>

            <ConditionSetEditor
              title="Что считаем (числитель)"
              value={form.numerator}
              onChange={(next) => setForm((f) => ({ ...f, numerator: next }))}
              attributes={attributes}
              personFields={personFields}
              periodWindows={periodWindows}
            />

            {form.calc_kind === 'ratio' && (
              <ConditionSetEditor
                title="С чем сравниваем (знаменатель)"
                value={form.denominator ?? EMPTY_CONDITION_SET}
                onChange={(next) => setForm((f) => ({ ...f, denominator: next }))}
                attributes={attributes}
                personFields={personFields}
                periodWindows={periodWindows}
              />
            )}

            {form.calc_kind === 'norm_to_fact' && (
              <Card size="small" title="Норматив к факту" style={{ marginTop: 12 }}>
                <Space orientation="vertical" style={{ width: '100%' }} size="small">
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    Норматив задаётся ниже, в разделе «Нормативы Cycle Time», на команду и квартал.
                    Фактический показатель считается по задачам числителя — по полю ниже.
                  </Text>
                  <div>
                    <Text type="secondary" style={{ fontSize: 11 }}>Поле факта</Text>
                    <Select
                      style={{ width: '100%' }}
                      placeholder="Выберите поле факта"
                      loading={attributesQuery.isLoading}
                      value={form.fact_field ?? undefined}
                      options={factFields.map((f) => ({ value: f.key, label: f.label }))}
                      onChange={(v) => setForm((f) => ({ ...f, fact_field: v }))}
                    />
                  </div>
                </Space>
              </Card>
            )}

            {form.calc_kind === 'score_to_max' && (
              <Card size="small" title="Средний балл к максимуму" style={{ marginTop: 12 }}>
                <Space orientation="vertical" style={{ width: '100%' }} size="small">
                  <div>
                    <Text type="secondary" style={{ fontSize: 11 }}>Поля с оценками (коды полей задачи)</Text>
                    <Select
                      mode="tags" style={{ width: '100%' }}
                      value={form.score_fields ?? []}
                      onChange={(v) => setForm((f) => ({ ...f, score_fields: v }))}
                      placeholder="rating_speed, rating_quality, rating_result"
                    />
                  </div>
                  <div>
                    <Text type="secondary" style={{ fontSize: 11 }}>Максимальный балл</Text>
                    <InputNumber
                      style={{ width: 120 }} min={1} value={form.score_max ?? 5}
                      onChange={(v) => setForm((f) => ({ ...f, score_max: v ?? 5 }))}
                    />
                  </div>
                </Space>
              </Card>
            )}

            <Card size="small" title="Инверсия и потолок" style={{ marginTop: 12 }}>
              <Space size="large">
                <Space>
                  <Switch checked={form.invert} onChange={(v) => setForm((f) => ({ ...f, invert: v }))} />
                  <Text>Инвертировать результат</Text>
                </Space>
                <Space>
                  <Switch checked={form.cap_at_100} onChange={(v) => setForm((f) => ({ ...f, cap_at_100: v }))} />
                  <Text>Ограничить сверху 100%</Text>
                </Space>
              </Space>
            </Card>

            <Button
              type="primary" style={{ marginTop: 16 }}
              loading={createMut.isPending || updateMut.isPending}
              onClick={save}
            >
              Сохранить метрику
            </Button>

            <MetricPreview form={form} />
          </>
        )}
      </div>

      {selectedId != null && (
        <aside
          style={{
            position: 'sticky', top: 16, background: t.cardBg, border: `1px solid ${t.border}`,
            borderRadius: 14, padding: 16,
          }}
        >
          <Title level={5} style={{ marginTop: 0, fontSize: 12, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
            Предпросмотр
          </Title>
          <div
            className="num"
            style={{
              fontSize: 13, fontWeight: 600, color: t.cyanPrimary, background: t.darkAccent,
              border: `1px solid ${t.border}`, borderRadius: 10, padding: 10, marginBottom: 10, lineHeight: 1.5,
            }}
          >
            {formulaText(form)}
          </div>
          <Text type="secondary" style={{ fontSize: 11.5, lineHeight: 1.5 }}>
            Числа по реальным задачам — в блоке «Предпросмотр на реальных данных» под формой:
            он считает то, что сейчас в форме, не сохраняя метрику.
          </Text>
        </aside>
      )}
    </div>
  );
}
