import { useRef, useState, type CSSProperties, type ReactNode } from 'react';
import { App, Button, InputNumber, Popover, Radio, Typography } from 'antd';
import { useChoosePlanSource } from '../../hooks/useBacklog';
import type { PlanChoiceBody } from '../../api/issues';
import type { EstimateCandidate, PlanRole } from '../../types/api';
import { MANUAL_CHOICE, defaultChoice, formatChoiceHours } from '../../utils/estimateDisputes';

const ROLE_TITLE: Record<PlanRole, string> = {
  analyst: 'Анализ', dev: 'Разработка', qa: 'Тестирование', opo: 'ОПЭ',
};

const optionStyle = (selected: boolean): CSSProperties => ({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 10,
  padding: '6px 10px',
  borderRadius: 8,
  cursor: 'pointer',
  border: `1px solid ${selected ? 'var(--accent-1, #1677ff)' : 'var(--glass-border, rgba(128,128,128,0.3))'}`,
  background: selected ? 'color-mix(in srgb, var(--accent-1, #1677ff) 12%, transparent)' : undefined,
});

function RoleChoice({ issueId, role, candidates, current, showTitle, onDone }: {
  issueId: string;
  role: PlanRole;
  candidates: EstimateCandidate[];
  current: number | null | undefined;
  showTitle: boolean;
  onDone?: () => void;
}) {
  const { notification } = App.useApp();
  const choose = useChoosePlanSource();
  const initial = defaultChoice(candidates, current);
  const [picked, setPicked] = useState(initial.picked);
  const [manual, setManual] = useState<number | null>(initial.manual);

  const value = picked === MANUAL_CHOICE
    ? manual
    : candidates.find((c) => c.source === picked)?.value ?? null;

  const accept = () => {
    if (value == null || choose.isPending) return;
    const body: PlanChoiceBody = picked === MANUAL_CHOICE
      ? { role, manual_value: value }
      : { role, source: picked };
    choose.mutate({ issueId, body }, {
      onSuccess: () => onDone?.(),
      onError: (e) => notification.error({ title: 'Не удалось сохранить выбор', description: e.message }),
    });
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {showTitle && <Typography.Text strong>{ROLE_TITLE[role]}</Typography.Text>}
      <Radio.Group
        name={`dispute-${issueId}-${role}`}
        value={picked}
        onChange={(e) => setPicked(e.target.value)}
        style={{ display: 'flex', flexDirection: 'column', gap: 6 }}
      >
        {candidates.map((c) => (
          <div key={c.source} style={optionStyle(picked === c.source)} onClick={() => setPicked(c.source)}>
            {/* Часы — внутри подписи варианта: диктор читает их вместе с названием поля. */}
            <Radio
              value={c.source}
              style={{ flex: 1 }}
              styles={{ label: { flex: 1, display: 'flex', justifyContent: 'space-between', gap: 10 } }}
            >
              <span>{c.label}</span>
              <Typography.Text strong style={{ whiteSpace: 'nowrap' }}>{formatChoiceHours(c.value)} ч</Typography.Text>
            </Radio>
          </div>
        ))}
        <div style={optionStyle(picked === MANUAL_CHOICE)} onClick={() => setPicked(MANUAL_CHOICE)}>
          <Radio value={MANUAL_CHOICE}>Ввести своё</Radio>
          <InputNumber
            size="small"
            min={0}
            value={manual}
            suffix="ч"
            aria-label={`${ROLE_TITLE[role]}: своё значение, часы`}
            style={{ width: 96 }}
            onFocus={() => setPicked(MANUAL_CHOICE)}
            onChange={(v) => setManual(v)}
            onPressEnter={accept}
          />
        </div>
      </Radio.Group>
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <Button size="small" type="primary" loading={choose.isPending} disabled={value == null} onClick={accept}>
          {value == null ? 'Принять' : `Принять ${formatChoiceHours(value)} ч`}
        </Button>
      </div>
    </div>
  );
}

/** Выбор значения по спорной оценке: одна роль (клик по ячейке) или все спорные
 *  роли задачи (клик по метке «спорно» — так доступна и скрытая ячейка ОПЭ). */
export default function EstimateDisputePopover({
  issueId, jiraKey, roles, candidates, current, ariaLabel, triggerStyle, children,
}: {
  issueId: string;
  jiraKey?: string | null;
  roles: PlanRole[];
  candidates: Partial<Record<PlanRole, EstimateCandidate[]>>;
  /** Действующие часы по ролям — их и отмечаем в выборе. */
  current: Partial<Record<PlanRole, number | null>>;
  ariaLabel: string;
  triggerStyle?: CSSProperties;
  /** Функция получает признак «поповер открыт» — чтобы спрятать подсказку
   *  ячейки: вложенная подсказка всплывает поверх поповера и закрывает «Принять». */
  children: ReactNode | ((open: boolean) => ReactNode);
}) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef<HTMLSpanElement>(null);
  const popupRef = useRef<HTMLDivElement>(null);
  const single = roles.length === 1;
  return (
    <Popover
      trigger="click"
      open={open}
      onOpenChange={setOpen}
      afterOpenChange={(visible) => {
        if (visible) {
          // С клавиатуры — сразу к отмеченному варианту, стрелки выбирают другой.
          popupRef.current?.querySelector<HTMLInputElement>('input[type="radio"]:checked')?.focus();
          return;
        }
        // Фокус остался в закрытом окне (Esc, «Принять») — вернуть его на ячейку.
        // Щёлкнули мимо, в другое поле, — фокус не отнимаем.
        const active = document.activeElement;
        if (!active || active === document.body || popupRef.current?.contains(active)) {
          triggerRef.current?.focus();
        }
      }}
      destroyOnHidden
      title={single ? `${ROLE_TITLE[roles[0]]} — оценки в Jira расходятся` : 'Оценки в Jira расходятся'}
      content={(
        <div ref={popupRef} style={{ width: 340, maxWidth: '100%', display: 'flex', flexDirection: 'column', gap: 12 }}>
          <Typography.Text type="secondary" style={{ fontSize: 12 }}>
            {jiraKey ? `${jiraKey}. ` : ''}Выберите верное значение. Выбор действует, пока в Jira не изменится одно из значений.
          </Typography.Text>
          {roles.map((role) => (
            <RoleChoice
              key={role}
              issueId={issueId}
              role={role}
              candidates={candidates[role] ?? []}
              current={current[role]}
              showTitle={!single}
              // Из общего списка решённая роль уходит сама, остальные ждут выбора.
              onDone={single ? () => setOpen(false) : undefined}
            />
          ))}
        </div>
      )}
    >
      <span
        ref={triggerRef}
        role="button"
        tabIndex={0}
        aria-label={ariaLabel}
        aria-expanded={open}
        style={{ cursor: 'pointer', ...triggerStyle }}
        onKeyDown={(e) => {
          if (e.key !== 'Enter' && e.key !== ' ') return;
          e.preventDefault();
          setOpen((o) => !o);
        }}
      >
        {typeof children === 'function' ? children(open) : children}
      </span>
    </Popover>
  );
}
