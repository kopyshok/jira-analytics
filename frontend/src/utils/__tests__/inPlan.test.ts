import { describe, it, expect } from 'vitest';
import type { BacklogChild, BacklogItemResponse } from '../../types/api';
import {
  countOffPlan, filterOffPlan, inPlanDisabled, inPlanHint, inPlanRole, isOffPlan,
  type InPlanRole, type InPlanRow,
} from '../inPlan';

const child = (id: string, included: boolean, role: InPlanRole = 'regular') =>
  ({ id, included_in_planning: included, in_plan_role: role }) as BacklogChild;

const row = (over: Partial<BacklogItemResponse>) =>
  ({
    id: 'r', included_in_planning: true, planning_mode: 'whole', in_plan_role: 'regular',
    has_children_in_backlog: false, children: [], ...over,
  }) as BacklogItemResponse;

describe('inPlanRole', () => {
  it('takes the role from the server, not from the list', () => {
    // Родитель чужой команды или на другой вкладке: эпик идёт корнем, без родителя в списке.
    expect(inPlanRole(row({ in_plan_role: 'inert' }))).toBe('inert');
    // Эпики спрятаны фильтром команды — инициатива всё равно по эпикам.
    expect(inPlanRole(row({ planning_mode: 'by_epics', in_plan_role: 'by_epics' }))).toBe('by_epics');
    expect(inPlanRole(row({ in_plan_role: 'by_epics_locked' }))).toBe('by_epics_locked');
  });

  it('child row keeps the server role', () => {
    expect(inPlanRole(child('e1', true, 'inert'))).toBe('inert');
    expect(inPlanRole(child('d1', false))).toBe('regular');
  });

  it('no role is regular', () => {
    expect(inPlanRole({})).toBe('regular');
  });

  it('mode chosen in the modal wins until the server answers', () => {
    expect(inPlanRole(row({ has_children_in_backlog: true }), 'by_epics')).toBe('by_epics');
    const byEpics = row({ has_children_in_backlog: true, planning_mode: 'by_epics', in_plan_role: 'by_epics' });
    expect(inPlanRole(byEpics, 'whole')).toBe('regular');
    expect(inPlanRole(byEpics, 'by_epics')).toBe('by_epics');
  });

  it('own mode does not change an epic of a whole initiative or a locked one', () => {
    expect(inPlanRole(row({ in_plan_role: 'inert' }), 'by_epics')).toBe('inert');
    expect(inPlanRole(row({ in_plan_role: 'by_epics_locked' }), 'whole')).toBe('by_epics_locked');
  });

  it('locked switch can be turned off but not on', () => {
    expect(inPlanDisabled('by_epics_locked', false)).toBe(true);
    expect(inPlanDisabled('by_epics_locked', true)).toBe(false);
    expect(inPlanDisabled('inert', true)).toBe(true);
    expect(inPlanDisabled('by_epics', false)).toBe(false);
  });
});

describe('inPlanHint', () => {
  it('switched-off initiative by epics: its epics go to the plan', () => {
    expect(inPlanHint('by_epics', false)).toBe(
      'Планируется по эпикам: в сценарий идут её эпики. Включите, чтобы добавить и саму инициативу',
    );
  });

  it('regular switched on goes to scenarios', () => {
    expect(inPlanHint('regular', true)).toBe('Попадает в сценарии');
  });

  it('regular switched off and switched-on initiative by epics', () => {
    expect(inPlanHint('regular', false)).toBe('Не попадает в сценарии');
    expect(inPlanHint('by_epics', true)).toBe('Попадает в сценарии');
  });

  it('inert and locked explain why the switch does not work', () => {
    expect(inPlanHint('inert', true)).toBe('Инициатива планируется целиком — часы эпиков уже в ней');
    expect(inPlanHint('by_epics_locked', false)).toBe('Инициатива нескольких команд планируется только по эпикам');
  });
});

describe('off-plan filter and count', () => {
  const rfaWhole = row({
    id: 'w', has_children_in_backlog: true,
    children: [child('e1', false, 'inert'), child('d1', false)],
  });
  const rfaByEpics = row({
    id: 'b', has_children_in_backlog: true, planning_mode: 'by_epics', in_plan_role: 'by_epics',
    included_in_planning: false,
    children: [child('e2', false), child('e3', true)],
  });
  const off = row({ id: 'o', included_in_planning: false });
  // Эпик инициативы «целиком», чей родитель в этот список не попал.
  const inertRoot = row({ id: 'x', included_in_planning: false, in_plan_role: 'inert' });
  const rows = [rfaWhole, rfaByEpics, off, inertRoot];
  const offPlan = (r: InPlanRow) => isOffPlan(inPlanRole(r), r.included_in_planning);

  it('counts only user choice', () => {
    // d1 (Дискавери), e2 (эпик по эпикам), o — да; e1 и x (внутри «целиком») и сама b — нет.
    expect(countOffPlan(rows, offPlan)).toBe(3);
  });

  it('locked initiative and initiative by epics with hidden epics are not off-plan', () => {
    const locked = row({ id: 'l', in_plan_role: 'by_epics_locked', included_in_planning: false });
    const hidden = row({
      id: 'h', planning_mode: 'by_epics', in_plan_role: 'by_epics', included_in_planning: false,
    });
    expect(countOffPlan([locked, hidden], offPlan)).toBe(0);
  });

  it('keeps parents only with off-plan children', () => {
    const shown = filterOffPlan(rows, offPlan)!;
    expect(shown.map((r) => r.id)).toEqual(['w', 'b', 'o']);
    expect(shown[0].children!.map((c) => c.id)).toEqual(['d1']);
    expect(shown[1].children!.map((c) => c.id)).toEqual(['e2']);
  });
});
