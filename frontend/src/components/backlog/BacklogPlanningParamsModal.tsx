import { useEffect, useMemo, useState } from 'react';
import { App, Button, Checkbox, Col, Divider, InputNumber, Modal, Radio, Row, Space, Tag, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useUpdateBacklogItem } from '../../hooks/useBacklog';
import { useHoursBreakdown } from '../../hooks/useHoursBreakdown';
import { useGlobalPeriod } from '../../hooks/useGlobalPeriod';
import { api } from '../../api/client';
import HoursBreakdownTable from '../hours/HoursBreakdownTable';
import PlanConflictBanner from '../hours/PlanConflictBanner';
import PlanEditDrawer from '../hours/PlanEditDrawer';
import type { BacklogItemResponse } from '../../types/api';

interface Props {
  open: boolean;
  item: BacklogItemResponse | null;
  onClose: () => void;
}

type PhaseKey = 'analyst' | 'dev' | 'qa' | 'launch';

const PHASE_LABELS: Record<PhaseKey, string> = {
  analyst: 'Анализ',
  dev: 'Разработка',
  qa: 'Тестирование (QA)',
  launch: 'ОПЭ',
};

interface FieldValue {
  effective: number | null;
  jira: number | null;
}

interface FormState {
  involvement: Record<PhaseKey, FieldValue>;
  duration: Record<PhaseKey, FieldValue>;
  parallel: Record<Exclude<PhaseKey, 'launch'>, FieldValue>;
}

function buildState(item: BacklogItemResponse | null): FormState {
  const i = item;
  return {
    involvement: {
      analyst: { effective: i?.involvement_analyst ?? null, jira: i?.involvement_analyst_jira ?? null },
      dev: { effective: i?.involvement_dev ?? null, jira: i?.involvement_dev_jira ?? null },
      qa: { effective: i?.involvement_qa ?? null, jira: i?.involvement_qa_jira ?? null },
      launch: { effective: i?.involvement_launch ?? null, jira: i?.involvement_launch_jira ?? null },
    },
    duration: {
      analyst: { effective: i?.duration_analyst_days ?? null, jira: i?.duration_analyst_days_jira ?? null },
      dev: { effective: i?.duration_dev_days ?? null, jira: i?.duration_dev_days_jira ?? null },
      qa: { effective: i?.duration_qa_days ?? null, jira: i?.duration_qa_days_jira ?? null },
      launch: { effective: i?.duration_launch_days ?? null, jira: i?.duration_launch_days_jira ?? null },
    },
    parallel: {
      analyst: { effective: i?.parallel_count_analyst ?? null, jira: null },
      dev: { effective: i?.parallel_count_dev ?? null, jira: null },
      qa: { effective: i?.parallel_count_qa ?? null, jira: null },
    },
  };
}

function SourceBadge({ effective, jira }: FieldValue) {
  if (effective === null && jira === null) return null;
  if (effective === jira) return <Tag color="cyan" style={{ marginLeft: 6 }}>Jira</Tag>;
  return <Tag color="gold" style={{ marginLeft: 6 }}>вручную</Tag>;
}

function PhaseRow({
  phase, state, onChange,
}: {
  phase: PhaseKey;
  state: FormState;
  onChange: (next: FormState) => void;
}) {
  const inv = state.involvement[phase];
  const dur = state.duration[phase];
  const par = phase === 'launch' ? null : state.parallel[phase];

  const setInv = (v: number | null) => onChange({
    ...state,
    involvement: { ...state.involvement, [phase]: { ...inv, effective: v } },
  });
  const setDur = (v: number | null) => onChange({
    ...state,
    duration: { ...state.duration, [phase]: { ...dur, effective: v } },
  });
  const setPar = (v: number | null) => {
    if (phase === 'launch') return;
    onChange({
      ...state,
      parallel: { ...state.parallel, [phase]: { ...par!, effective: v } },
    });
  };

  const resetInv = () => setInv(inv.jira);
  const resetDur = () => setDur(dur.jira);

  const labelStyle: React.CSSProperties = { width: 160, display: 'inline-block' };
  return (
    <div style={{ marginBottom: 16 }}>
      <Typography.Title level={5} style={{ marginTop: 0, marginBottom: 8 }}>
        {PHASE_LABELS[phase]}
      </Typography.Title>
      <Space orientation="vertical" size={6} style={{ width: '100%' }}>
        <Space style={{ width: '100%' }}>
          <span style={labelStyle}>Вовлечённость (0–1)</span>
          <InputNumber
            value={inv.effective}
            onChange={setInv}
            min={0}
            max={1}
            step={0.05}
            style={{ width: 100 }}
            placeholder={inv.jira != null ? String(inv.jira) : '—'}
          />
          <SourceBadge {...inv} />
          {inv.jira !== null && inv.effective !== inv.jira && (
            <Button size="small" icon={<ReloadOutlined />} onClick={resetInv}>
              К Jira
            </Button>
          )}
        </Space>
        <Space style={{ width: '100%' }}>
          <span style={labelStyle}>Длительность (дней)</span>
          <InputNumber
            value={dur.effective}
            onChange={setDur}
            min={0}
            step={1}
            style={{ width: 100 }}
            placeholder={dur.jira != null ? String(dur.jira) : '—'}
          />
          <SourceBadge {...dur} />
          {dur.jira !== null && dur.effective !== dur.jira && (
            <Button size="small" icon={<ReloadOutlined />} onClick={resetDur}>
              К Jira
            </Button>
          )}
        </Space>
        {par && (
          <Space style={{ width: '100%' }}>
            <span style={labelStyle}>Параллельность</span>
            <InputNumber
              value={par.effective}
              onChange={setPar}
              min={1}
              max={5}
              step={1}
              style={{ width: 100 }}
              placeholder="1"
            />
          </Space>
        )}
      </Space>
    </div>
  );
}

export default function BacklogPlanningParamsModal({ open, item, onClose }: Props) {
  const { notification } = App.useApp();
  const update = useUpdateBacklogItem();
  const initial = useMemo(() => buildState(item), [item]);
  const [state, setState] = useState<FormState>(initial);
  const [editPlanOpen, setEditPlanOpen] = useState(false);
  // Локальное (оптимистичное) состояние переключателя — Radio.Group контролируемый,
  // а item-проп приходит снимком и не обновляется пока модалка открыта. Без этого
  // выбор визуально «не нажимается» до перезагрузки списка.
  const [mode, setMode] = useState<'whole' | 'by_epics'>('whole');
  const [included, setIncluded] = useState(true);
  const [seededItemId, setSeededItemId] = useState<string | undefined>(undefined);

  const qc = useQueryClient();
  const { period } = useGlobalPeriod();

  useEffect(() => {
    setState(buildState(item));
  }, [item]);

  // Пересеять оптимистичное состояние переключателя при смене задачи
  // (adjust-during-render — рекомендация React вместо setState внутри effect).
  if (item?.id !== seededItemId) {
    setSeededItemId(item?.id);
    setMode((item?.planning_mode as 'whole' | 'by_epics') ?? 'whole');
    setIncluded(item?.included_in_planning ?? true);
  }

  const issueId = item?.issue_id ?? null;
  const hasChildren = !!item?.has_children_in_backlog;
  const backlogItemId = item?.id ?? '';

  const { data: hoursData, isLoading: hoursLoading } = useHoursBreakdown(
    issueId,
    period.year,
    period.quarter,
  );

  const modeMut = useMutation({
    mutationFn: (next: 'whole' | 'by_epics') =>
      api.patch(`/backlog/${backlogItemId}/planning-mode`, { mode: next }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['backlog'] }); },
    onError: (e) => {
      setMode((item?.planning_mode as 'whole' | 'by_epics') ?? 'whole');
      setIncluded(item?.included_in_planning ?? true);
      notification.error({ title: 'Ошибка', description: (e as Error).message });
    },
  });

  const incMut = useMutation({
    mutationFn: (val: boolean) =>
      api.patch(`/backlog/${backlogItemId}/included`, { included: val }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['backlog'] }); },
    onError: (e) => {
      setIncluded(item?.included_in_planning ?? true);
      notification.error({ title: 'Ошибка', description: (e as Error).message });
    },
  });

  const changeMode = (next: 'whole' | 'by_epics') => {
    setMode(next);
    setIncluded(next !== 'by_epics'); // совпадает с дефолтом на бэке
    modeMut.mutate(next);
  };

  const changeIncluded = (val: boolean) => {
    setIncluded(val);
    incMut.mutate(val);
  };

  const handleSave = () => {
    if (!item) return;
    const patch: Record<string, number | null> = {};
    const phases: PhaseKey[] = ['analyst', 'dev', 'qa', 'launch'];
    for (const ph of phases) {
      if (state.involvement[ph].effective !== initial.involvement[ph].effective) {
        patch[`involvement_${ph}`] = state.involvement[ph].effective;
      }
      if (state.duration[ph].effective !== initial.duration[ph].effective) {
        patch[`duration_${ph}_days`] = state.duration[ph].effective;
      }
    }
    for (const ph of ['analyst', 'dev', 'qa'] as const) {
      if (state.parallel[ph].effective !== initial.parallel[ph].effective) {
        patch[`parallel_count_${ph}`] = state.parallel[ph].effective;
      }
    }
    if (Object.keys(patch).length === 0) {
      onClose();
      return;
    }
    update.mutate(
      { id: item.id, data: patch },
      {
        onSuccess: () => {
          notification.success({ title: 'Параметры сохранены' });
          onClose();
        },
        onError: (e) => notification.error({ title: 'Ошибка', description: (e as Error).message }),
      },
    );
  };

  return (
    <>
      <Modal
        open={open}
        onCancel={onClose}
        onOk={handleSave}
        okText="Сохранить"
        cancelText="Отмена"
        confirmLoading={update.isPending}
        title={item ? `Параметры планирования — ${item.jira_key ?? ''} ${item.title}`.trim() : 'Параметры планирования'}
        width={900}
        destroyOnHidden
      >
        <Typography.Paragraph type="secondary" style={{ marginTop: 0 }}>
          Если поле в Jira пустое — заполни вручную. Ручная правка перетирает Jira-значение
          только пока оно пустое; если Jira потом получит значение, оно его перезапишет.
        </Typography.Paragraph>
        <Divider style={{ margin: '8px 0 16px' }} />
        <Row gutter={24}>
          <Col xs={24} md={12}>
            <PhaseRow phase="analyst" state={state} onChange={setState} />
            <PhaseRow phase="dev" state={state} onChange={setState} />
          </Col>
          <Col xs={24} md={12}>
            <PhaseRow phase="qa" state={state} onChange={setState} />
            <PhaseRow phase="launch" state={state} onChange={setState} />
          </Col>
        </Row>

        {issueId && (
          <>
            <Divider style={{ margin: '20px 0 12px' }} />
            <Typography.Title level={4} style={{ marginTop: 0, marginBottom: 12 }}>
              Часы и иерархия
            </Typography.Title>

            <PlanConflictBanner issueId={issueId} />

            {hasChildren && (
              <Space orientation="vertical" style={{ width: '100%', marginBottom: 12 }}>
                <Radio.Group
                  value={mode}
                  onChange={(e) => changeMode(e.target.value as 'whole' | 'by_epics')}
                  optionType="button"
                >
                  <Radio.Button value="whole">RFA целиком</Radio.Button>
                  <Radio.Button value="by_epics">По Эпикам</Radio.Button>
                </Radio.Group>
                {mode === 'by_epics' && (
                  <Checkbox
                    checked={included}
                    onChange={(e) => changeIncluded(e.target.checked)}
                  >
                    Включить саму RFA (для непокрытых кварталов)
                  </Checkbox>
                )}
              </Space>
            )}

            {hoursData && <HoursBreakdownTable data={hoursData} loading={hoursLoading} />}

            <Button style={{ marginTop: 12 }} onClick={() => setEditPlanOpen(true)}>
              ✎ Редактировать план
            </Button>
          </>
        )}
      </Modal>

      {issueId && (
        <PlanEditDrawer
          open={editPlanOpen}
          onClose={() => setEditPlanOpen(false)}
          issueId={issueId}
          issueKey={item?.jira_key ?? item?.title ?? ''}
          jiraValues={{
            analyst: item?.estimate_analyst_hours ?? null,
            dev: item?.estimate_dev_hours ?? null,
            qa: item?.estimate_qa_hours ?? null,
            opo: item?.estimate_opo_hours ?? null,
          }}
          effectiveValues={{
            analyst: item?.estimate_analyst_hours ?? null,
            dev: item?.estimate_dev_hours ?? null,
            qa: item?.estimate_qa_hours ?? null,
            opo: item?.estimate_opo_hours ?? null,
          }}
        />
      )}
    </>
  );
}
