import { useState } from 'react';
import { App, Alert, Button, Drawer, Progress, Select, Space, Typography } from 'antd';
import { CheckCircleFilled, MinusCircleOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router';
import { formatDateOnly } from '../utils/format';
import type { OnboardingStatus } from '../api/onboarding';
import { useOnboarding } from './OnboardingContext';
import { INTRO_STEPS, SETUP_STEPS, isClosed, type SetupStep } from './steps';

type RowState = 'done' | 'skipped' | 'pending';

function StatusIcon({ state, index }: { state: RowState; index?: number }) {
  if (state === 'done') return <CheckCircleFilled style={{ color: '#52c41a', fontSize: 18 }} />;
  if (state === 'skipped') return <MinusCircleOutlined style={{ color: 'var(--text-muted)', fontSize: 18 }} />;
  return (
    <span style={{
      display: 'inline-grid', placeItems: 'center', width: 18, height: 18, borderRadius: '50%',
      border: '1px solid var(--text-muted)', fontSize: 11, color: 'var(--text-2)',
    }}>{index ?? ''}</span>
  );
}

/** Состояния всех листьев шага: у листа — своё, у группы — состояния всех подпунктов. */
function leafStates(step: SetupStep, status: OnboardingStatus | undefined): RowState[] {
  if (step.children) return step.children.flatMap(c => leafStates(c, status));
  return [status?.steps[step.id]?.state ?? 'pending'];
}

/** Группа закрыта, только когда закрыты все подпункты: пропущена — если пропущены
 * все, иначе выполнена (значит, хотя бы один подпункт отмечен, а не пропущен). */
function groupState(step: SetupStep, status: OnboardingStatus | undefined): RowState {
  const states = leafStates(step, status);
  if (states.some(s => s === 'pending')) return 'pending';
  return states.every(s => s === 'skipped') ? 'skipped' : 'done';
}

function StepRow({ step, index, nested }: { step: SetupStep; index?: number; nested?: boolean }) {
  const { status, startTour, closePanel, setStepState } = useOnboarding();
  const { message } = App.useApp();
  const navigate = useNavigate();
  // «Проверил» и «Пропустить» — разные действия, каждое со своим busy, иначе
  // клик по одной кнопке подсвечивает загрузкой и вторую.
  const [busyAction, setBusyAction] = useState<RowState | null>(null);
  const closed = isClosed(step, status);
  const own = step.children ? undefined : status?.steps[step.id];
  const state: RowState = step.children ? groupState(step, status) : (own?.state ?? 'pending');

  const act = async (next: RowState) => {
    setBusyAction(next);
    try {
      await setStepState(step.id, next);
    } catch {
      message.error('Не удалось сохранить отметку');
    } finally {
      setBusyAction(null);
    }
  };

  const note = own && own.state !== 'pending' && own.marked_at
    ? own.source === 'auto'
      ? `Выполнено автоматически · ${formatDateOnly(own.marked_at)}`
      : `${own.state === 'skipped' ? 'Пропущено' : 'Отмечено'}: ${own.marked_by ?? '—'}, ${formatDateOnly(own.marked_at)}`
    : null;

  return (
    <div style={{ display: 'flex', gap: 10, padding: nested ? '6px 0' : '10px 0' }} data-testid={`onboarding-step-${step.id}`}>
      <div style={{ paddingTop: 2 }}><StatusIcon state={state} index={index} /></div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <Typography.Text strong={!nested} delete={state === 'skipped'}>{step.title}</Typography.Text>
        {!closed && <div><Typography.Text type="secondary" style={{ fontSize: 12 }}>{step.hint}</Typography.Text></div>}
        {note && <div><Typography.Text type="secondary" style={{ fontSize: 12 }}>{note}</Typography.Text></div>}
        <Space size={4} wrap style={{ marginTop: 6 }}>
          {step.tourId && (
            <Button size="small" type="primary" ghost onClick={() => startTour(step.tourId as string)} data-testid={`tour-start-${step.tourId}`}>
              Показать
            </Button>
          )}
          {step.route && (
            <Button size="small" onClick={() => { closePanel(); navigate(step.route as string); }}>Перейти</Button>
          )}
          {!step.children && state === 'pending' && step.manual && (
            <Button size="small" loading={busyAction === 'done'} onClick={() => act('done')}>Проверил</Button>
          )}
          {!step.children && state === 'pending' && (
            <Button size="small" type="text" loading={busyAction === 'skipped'} onClick={() => act('skipped')}>Пропустить</Button>
          )}
          {!step.children && (state === 'skipped' || (state === 'done' && own?.source === 'manual')) && (
            <Button size="small" type="text" loading={busyAction === 'pending'} onClick={() => act('pending')}>Вернуть</Button>
          )}
        </Space>
        {step.children?.map(c => <StepRow key={c.id} step={c} nested />)}
      </div>
    </div>
  );
}

export default function OnboardingDrawer() {
  const { team, teamOptions, setTeam, status, panelOpen, closePanel, startTour, updateMe } = useOnboarding();
  const { message } = App.useApp();
  const [showDoneSetup, setShowDoneSetup] = useState(false);
  const tours = new Set(status?.me.completed_tours ?? []);
  const setupDone = SETUP_STEPS.filter(s => isClosed(s, status)).length;
  const setupComplete = setupDone === SETUP_STEPS.length;

  return (
    <Drawer
      title="Первые шаги"
      open={panelOpen}
      onClose={closePanel}
      placement="right"
      styles={{ wrapper: { width: 'min(520px, 92vw)' } }}
      footer={
        <Button
          type="link"
          size="small"
          onClick={() => {
            void updateMe({ hidden: true }).catch(() => message.error('Не удалось сохранить настройку'));
            closePanel();
          }}
        >
          Больше не показывать (вернуть — кнопкой «Первые шаги» в справке)
        </Button>
      }
    >
      <Typography.Title level={5} style={{ marginTop: 0 }}>Настройка команды</Typography.Title>
      {teamOptions.length === 0 && (
        <Alert type="info" showIcon title="Выберите команду в шапке, чтобы увидеть шаги её настройки." />
      )}
      {teamOptions.length > 1 && (
        <Select
          value={team ?? undefined}
          onChange={setTeam}
          options={teamOptions.map(t => ({ value: t, label: t }))}
          style={{ width: '100%', marginBottom: 8 }}
        />
      )}
      {team && (
        <>
          <Progress
            percent={Math.round((setupDone / SETUP_STEPS.length) * 100)}
            format={() => `${setupDone} из ${SETUP_STEPS.length}`}
          />
          {setupComplete && !showDoneSetup ? (
            <div style={{ padding: '8px 0' }}>
              <Typography.Text>Команда настроена.</Typography.Text>{' '}
              <Button type="link" size="small" onClick={() => setShowDoneSetup(true)}>Показать шаги</Button>
            </div>
          ) : (
            SETUP_STEPS.map((s, i) => <StepRow key={s.id} step={s} index={i + 1} />)
          )}
        </>
      )}

      <Typography.Title level={5} style={{ marginTop: 24 }}>Знакомство с сервисом</Typography.Title>
      {INTRO_STEPS.map(s => (
        <div key={s.tourId} style={{ display: 'flex', gap: 10, padding: '10px 0' }}>
          <div style={{ paddingTop: 2 }}><StatusIcon state={tours.has(s.tourId) ? 'done' : 'pending'} /></div>
          <div style={{ flex: 1 }}>
            <Typography.Text strong>{s.title}</Typography.Text>
            <div><Typography.Text type="secondary" style={{ fontSize: 12 }}>{s.hint}</Typography.Text></div>
            <Button size="small" type="primary" ghost style={{ marginTop: 6 }} onClick={() => startTour(s.tourId)} data-testid={`tour-start-${s.tourId}`}>
              {tours.has(s.tourId) ? 'Показать ещё раз' : 'Показать'}
            </Button>
          </div>
        </div>
      ))}
    </Drawer>
  );
}
