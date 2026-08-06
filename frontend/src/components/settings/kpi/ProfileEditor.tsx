import { useEffect, useState } from 'react';
import {
  App, Button, Card, Input, InputNumber, Popconfirm, Select, Space, Switch, Table, Tag, Typography,
} from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons';
import { useThemeTokens } from '../../../aurora/theme/useThemeTokens';
import { useRoles } from '../../../hooks/useRoles';
import {
  createProfile, deleteProfile, fetchCoverage, fetchMetrics, fetchProfiles, updateProfile,
  type KpiCoverageRow, type KpiProfileDef, type KpiProfileMetricPayload, type KpiProfilePayload,
} from '../../../api/kpi';

const { Text } = Typography;

function blankProfileForm(): KpiProfilePayload {
  return {
    code: '', name: '', role_codes: [], target_pct: 80, warn_band_pct: 10,
    is_enabled: true, metrics: [],
  };
}

export default function ProfileEditor() {
  const { notification } = App.useApp();
  const qc = useQueryClient();
  const t = useThemeTokens();

  const profilesQuery = useQuery({ queryKey: ['kpi-settings', 'profiles'], queryFn: fetchProfiles });
  const metricsQuery = useQuery({ queryKey: ['kpi-settings', 'metrics'], queryFn: fetchMetrics });
  const coverageQuery = useQuery({ queryKey: ['kpi-settings', 'coverage'], queryFn: fetchCoverage });
  const { data: roles } = useRoles();

  const [selectedId, setSelectedId] = useState<string | 'new' | null>(null);
  const [form, setForm] = useState<KpiProfilePayload>(blankProfileForm());

  useEffect(() => {
    if (!profilesQuery.data || selectedId !== null) return;
    if (profilesQuery.data.length > 0) setSelectedId(profilesQuery.data[0].id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profilesQuery.data]);

  useEffect(() => {
    if (selectedId === 'new' || selectedId === null) return;
    const p = profilesQuery.data?.find((x) => x.id === selectedId);
    if (p) {
      setForm({
        code: p.code, name: p.name, role_codes: p.role_codes, target_pct: p.target_pct,
        warn_band_pct: p.warn_band_pct, is_enabled: p.is_enabled,
        metrics: p.metrics.map((m) => ({ metric_code: m.metric_code, weight: m.weight, sort_order: m.sort_order })),
      });
    }
  }, [selectedId, profilesQuery.data]);

  const startNew = () => { setSelectedId('new'); setForm(blankProfileForm()); };

  // Правка профиля (веса, цель, жёлтая зона) меняет результат уже открытой
  // ведомости — она должна пересчитаться, а не оставаться со старыми
  // числами до перезагрузки страницы (см. ревью, ВАЖНО 7).
  const createMut = useMutation({
    mutationFn: (body: KpiProfilePayload) => createProfile(body),
    onSuccess: (p: KpiProfileDef) => {
      qc.invalidateQueries({ queryKey: ['kpi-settings', 'profiles'] });
      qc.invalidateQueries({ queryKey: ['kpi-settings', 'coverage'] });
      qc.invalidateQueries({ queryKey: ['kpi'] });
      notification.success({ title: 'Профиль создан' });
      setSelectedId(p.id);
    },
    onError: (e: Error) => notification.error({ title: 'Не удалось сохранить', description: e.message }),
  });
  const updateMut = useMutation({
    mutationFn: (body: KpiProfilePayload) => updateProfile(selectedId as string, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['kpi-settings', 'profiles'] });
      qc.invalidateQueries({ queryKey: ['kpi-settings', 'coverage'] });
      qc.invalidateQueries({ queryKey: ['kpi'] });
      notification.success({ title: 'Профиль сохранён' });
    },
    onError: (e: Error) => notification.error({ title: 'Не удалось сохранить', description: e.message }),
  });
  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteProfile(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['kpi-settings', 'profiles'] });
      qc.invalidateQueries({ queryKey: ['kpi-settings', 'coverage'] });
      qc.invalidateQueries({ queryKey: ['kpi'] });
      notification.success({ title: 'Профиль удалён' });
      setSelectedId(null);
    },
    onError: (e: Error) => notification.error({ title: 'Не удалось удалить', description: e.message }),
  });

  const weightSumPct = Math.round(form.metrics.reduce((s, m) => s + m.weight, 0) * 1000) / 10;
  const sumOk = Math.abs(weightSumPct - 100) < 0.1;

  const updateWeight = (code: string, pct: number) => {
    setForm((f) => ({
      ...f,
      metrics: f.metrics.map((m) => (m.metric_code === code ? { ...m, weight: pct / 100 } : m)),
    }));
  };
  const removeMetric = (code: string) => {
    setForm((f) => ({ ...f, metrics: f.metrics.filter((m) => m.metric_code !== code) }));
  };
  const addMetric = (code: string) => {
    setForm((f) => ({
      ...f,
      metrics: [...f.metrics, { metric_code: code, weight: 0, sort_order: f.metrics.length }],
    }));
  };

  const save = () => {
    if (!sumOk) return;
    if (selectedId === 'new') createMut.mutate(form);
    else if (selectedId) updateMut.mutate(form);
  };

  const metricsByCode = new Map((metricsQuery.data ?? []).map((m) => [m.code, m]));
  const availableToAdd = (metricsQuery.data ?? []).filter(
    (m) => !form.metrics.some((fm) => fm.metric_code === m.code),
  );

  const columns = [
    {
      title: 'Метрика', dataIndex: 'metric_code',
      render: (code: string) => metricsByCode.get(code)?.name ?? code,
    },
    {
      title: 'Способ расчёта', dataIndex: 'metric_code',
      render: (code: string) => {
        const kind = metricsByCode.get(code)?.calc_kind;
        return kind === 'ratio' ? 'Доля' : kind === 'norm_to_fact' ? 'Норматив к факту'
          : kind === 'score_to_max' ? 'Средний балл к максимуму' : '—';
      },
    },
    {
      title: 'Вес', width: 140,
      render: (_: unknown, r: KpiProfileMetricPayload) => (
        <Space>
          <InputNumber
            size="small" min={0} max={100} step={1}
            value={Math.round(r.weight * 1000) / 10}
            onChange={(v) => updateWeight(r.metric_code, v ?? 0)}
          />
          %
        </Space>
      ),
    },
    {
      title: '', width: 40,
      render: (_: unknown, r: KpiProfileMetricPayload) => (
        <Button size="small" icon={<DeleteOutlined />} onClick={() => removeMetric(r.metric_code)} />
      ),
    },
  ];

  return (
    <div>
      <Space wrap style={{ marginBottom: 12 }}>
        {(profilesQuery.data ?? []).map((p) => (
          <Button
            key={p.id}
            type={selectedId === p.id ? 'primary' : 'default'}
            onClick={() => setSelectedId(p.id)}
          >
            {p.name}{p.role_codes.length ? ` · ролей: ${p.role_codes.length}` : ' · без ролей'}
          </Button>
        ))}
        <Button icon={<PlusOutlined />} onClick={startNew}>Создать профиль</Button>
      </Space>

      {selectedId == null ? (
        <Text type="secondary">Профилей пока нет — создайте первый.</Text>
      ) : (
        <>
          <Card size="small" title="Основное" style={{ marginBottom: 12 }}>
            <Space wrap size="middle">
              <div>
                <Text type="secondary" style={{ fontSize: 11 }}>Код</Text><br />
                <Input
                  style={{ width: 160 }} value={form.code}
                  onChange={(e) => setForm((f) => ({ ...f, code: e.target.value }))}
                />
              </div>
              <div>
                <Text type="secondary" style={{ fontSize: 11 }}>Название</Text><br />
                <Input
                  style={{ width: 220 }} value={form.name}
                  onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                />
              </div>
              <div>
                <Text type="secondary" style={{ fontSize: 11 }}>Роли сотрудников</Text><br />
                <Select
                  mode="multiple" allowClear style={{ minWidth: 280 }}
                  placeholder="Кого оценивает профиль"
                  options={(roles ?? []).filter((r) => r.is_active).map((r) => ({ value: r.code, label: r.label }))}
                  value={form.role_codes}
                  onChange={(v: string[]) => setForm((f) => ({ ...f, role_codes: v }))}
                />
              </div>
              <div>
                <Text type="secondary" style={{ fontSize: 11 }}>Целевой уровень, %</Text><br />
                <InputNumber
                  style={{ width: 100 }} min={0} max={100} value={form.target_pct}
                  onChange={(v) => setForm((f) => ({ ...f, target_pct: v ?? 80 }))}
                />
              </div>
              <div>
                <Text type="secondary" style={{ fontSize: 11 }}>Жёлтая зона, п.п. от цели</Text><br />
                <InputNumber
                  style={{ width: 100 }} min={0} max={100} value={form.warn_band_pct}
                  onChange={(v) => setForm((f) => ({ ...f, warn_band_pct: v ?? 10 }))}
                />
              </div>
              <div>
                <Text type="secondary" style={{ fontSize: 11 }}>Включён</Text><br />
                <Switch checked={form.is_enabled} onChange={(v) => setForm((f) => ({ ...f, is_enabled: v }))} />
              </div>
            </Space>
            <Text type="secondary" style={{ fontSize: 11.5, display: 'block', marginTop: 10 }}>
              Одна роль принадлежит не более чем одному профилю — иначе выбор профиля был бы
              неоднозначным. Сотрудники ролей вне профилей в ведомость не попадают.
            </Text>
          </Card>

          <Card
            size="small"
            title="Метрики профиля"
            extra={(
              <Select
                key={form.metrics.length}
                size="small" style={{ width: 220 }} placeholder="Добавить метрику"
                options={availableToAdd.map((m) => ({ value: m.code, label: m.name }))}
                onSelect={(v: string) => addMetric(v)}
              />
            )}
          >
            <div
              style={{
                display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', marginBottom: 10,
                borderRadius: 10, background: sumOk ? t.darkAccent : `color-mix(in srgb, ${t.danger} 12%, transparent)`,
                border: `1px solid ${sumOk ? t.border : t.danger}`,
              }}
            >
              <div style={{ flex: 1, height: 8, borderRadius: 999, background: t.darkRows, overflow: 'hidden' }}>
                <div
                  style={{
                    height: '100%', width: `${Math.min(100, Math.max(0, weightSumPct))}%`,
                    background: sumOk ? t.success : t.danger,
                  }}
                />
              </div>
              <Text style={{ fontSize: 12.5, fontWeight: 700, color: sumOk ? t.success : t.danger }}>
                {sumOk ? `Сумма весов: ${weightSumPct}% — сходится` : `Сумма весов: ${weightSumPct}% — нужно ровно 100%`}
              </Text>
            </div>
            <Table
              dataSource={form.metrics}
              rowKey="metric_code"
              size="small"
              pagination={false}
              columns={columns}
            />
          </Card>

          <Space style={{ marginTop: 16 }}>
            <Button
              type="primary" disabled={!sumOk}
              loading={createMut.isPending || updateMut.isPending}
              onClick={save}
            >
              Сохранить профиль
            </Button>
            {selectedId !== 'new' && (
              <Popconfirm
                title="Удалить профиль?" onConfirm={() => deleteMut.mutate(selectedId as string)}
                okText="Удалить" cancelText="Отмена"
              >
                <Button danger icon={<DeleteOutlined />} loading={deleteMut.isPending}>Удалить профиль</Button>
              </Popconfirm>
            )}
          </Space>
        </>
      )}

      {/* Профиля «по умолчанию» больше нет: сотрудник с непривязанной или
          незаполненной ролью молча исчезает из ведомости. Эта таблица —
          единственный способ увидеть, кого потеряли. */}
      <Card size="small" title="Покрытие ролей профилями" style={{ marginTop: 20 }}>
        <Table<KpiCoverageRow>
          dataSource={coverageQuery.data?.rows ?? []}
          loading={coverageQuery.isLoading}
          rowKey={(r) => r.role_code ?? '__none__'}
          size="small"
          pagination={false}
          columns={[
            { title: 'Роль', dataIndex: 'role_label' },
            { title: 'Сотрудников', dataIndex: 'employee_count', width: 120, align: 'right' },
            {
              title: 'Профиль оценки',
              render: (_: unknown, r: KpiCoverageRow) => (
                r.profile_name
                  ? <Tag color="cyan">{r.profile_name}</Tag>
                  : <Text type="secondary">не привязана</Text>
              ),
            },
            {
              title: 'В ведомости', width: 170,
              render: (_: unknown, r: KpiCoverageRow) => (
                r.profile_name
                  ? <Tag color="success">оценивается</Tag>
                  : <Tag color={r.role_code ? 'default' : 'warning'}>
                      {r.role_code ? 'не показывается' : 'проверить карточки'}
                    </Tag>
              ),
            },
          ]}
        />
        {coverageQuery.data && (
          <Text type="secondary" style={{ fontSize: 12, display: 'block', marginTop: 9 }}>
            Оценивается {coverageQuery.data.evaluated_count} человек
            из {coverageQuery.data.total_count}. Остальные в ведомость не попадают.
          </Text>
        )}
      </Card>
    </div>
  );
}
