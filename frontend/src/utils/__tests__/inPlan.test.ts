import { describe, it, expect } from 'vitest';
import type { BacklogChild, BacklogItemResponse } from '../../types/api';
import {
  countOffPlan, filterOffPlan, inertEpicIds, inPlanDisabled, inPlanRole, isOffPlan,
  type InPlanRow,
} from '../inPlan';

const child = (id: string, included: boolean, service = false) =>
  ({ id, included_in_planning: included, is_service_epic: service }) as BacklogChild;

const row = (over: Partial<BacklogItemResponse>) =>
  ({
    id: 'r', included_in_planning: true, planning_mode: 'whole',
    has_children_in_backlog: false, children: [], ...over,
  }) as BacklogItemResponse;

describe('inertEpicIds', () => {
  it('marks ordinary epics of a whole RFA, not Discovery', () => {
    const rfa = row({ id: 'rfa', has_children_in_backlog: true, children: [child('e1', true), child('d1', false, true)] });
    expect([...inertEpicIds([rfa])]).toEqual(['e1']);
  });

  it('ignores RFA planned by epics, including forced multi-team', () => {
    const byEpics = row({ planning_mode: 'by_epics', children: [child('e1', true)] });
    const locked = row({ planning_mode_locked: true, children: [child('e2', true)] });
    expect(inertEpicIds([byEpics, locked]).size).toBe(0);
  });
});

describe('inPlanRole', () => {
  it('by-epics parent with children', () => {
    expect(inPlanRole(row({ has_children_in_backlog: true, planning_mode: 'by_epics' }), false)).toBe('by_epics');
  });

  it('lock comes from the server, not from children in the list', () => {
    // Фильтр команды спрятал дочек чужой команды — сервер всё равно блокирует.
    expect(inPlanRole(row({ planning_mode_locked: true, include_locked: true }), false)).toBe('by_epics_locked');
    // Дети в списке есть, но сервер включить разрешает.
    expect(
      inPlanRole(row({ has_children_in_backlog: true, planning_mode_locked: true, include_locked: false }), false),
    ).toBe('by_epics');
  });

  it('server lock applies to a child row too', () => {
    expect(inPlanRole({ include_locked: true }, false)).toBe('by_epics_locked');
  });

  it('by-epics without children in list is regular', () => {
    expect(inPlanRole(row({ planning_mode: 'by_epics' }), false)).toBe('regular');
  });

  it('local mode from the modal wins', () => {
    expect(inPlanRole(row({ has_children_in_backlog: true }), false, 'by_epics')).toBe('by_epics');
  });

  it('locked switch can be turned off but not on', () => {
    expect(inPlanDisabled('by_epics_locked', false)).toBe(true);
    expect(inPlanDisabled('by_epics_locked', true)).toBe(false);
    expect(inPlanDisabled('inert', true)).toBe(true);
  });
});

describe('off-plan filter and count', () => {
  const rfaWhole = row({
    id: 'w', has_children_in_backlog: true,
    children: [child('e1', false), child('d1', false, true)],
  });
  const rfaByEpics = row({
    id: 'b', has_children_in_backlog: true, planning_mode: 'by_epics', included_in_planning: false,
    children: [child('e2', false), child('e3', true)],
  });
  const off = row({ id: 'o', included_in_planning: false });
  const rows = [rfaWhole, rfaByEpics, off];
  const inert = inertEpicIds(rows);
  const offPlan = (r: InPlanRow) => isOffPlan(inPlanRole(r, inert.has(r.id)), r.included_in_planning);

  it('counts only user choice', () => {
    // d1 (Дискавери), e2 (эпик по эпикам), o — да; e1 (внутри «целиком») и сама b — нет.
    expect(countOffPlan(rows, offPlan)).toBe(3);
  });

  it('server-locked initiative is not off-plan even without children in the list', () => {
    const locked = row({ id: 'l', planning_mode_locked: true, include_locked: true, included_in_planning: false });
    expect(countOffPlan([locked], offPlan)).toBe(0);
  });

  it('keeps parents only with off-plan children', () => {
    const shown = filterOffPlan(rows, offPlan)!;
    expect(shown.map((r) => r.id)).toEqual(['w', 'b', 'o']);
    expect(shown[0].children!.map((c) => c.id)).toEqual(['d1']);
    expect(shown[1].children!.map((c) => c.id)).toEqual(['e2']);
  });
});
