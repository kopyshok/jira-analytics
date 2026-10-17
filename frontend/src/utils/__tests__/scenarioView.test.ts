import { describe, expect, it } from 'vitest';
import {
  capacityBar, formatHours, personInitials, roleHoursTotals, roleShortLabel, scenarioRowState,
} from '../scenarioView';
import { rolesAffectedByAllocation } from '../planning';
import type { AllocationResponse } from '../../types/api';

const alloc = (p: Partial<AllocationResponse>): AllocationResponse =>
  ({
    included: true,
    estimate_analyst_hours: 60,
    estimate_dev_hours: 40,
    estimate_qa_hours: 20,
    estimate_opo_hours: 10,
    override_estimate_analyst_hours: null,
    override_estimate_dev_hours: null,
    override_estimate_qa_hours: null,
    override_estimate_opo_hours: null,
    opo_analyst_ratio: 0.5,
    assignee_employee_id: null,
    assignee_role: null,
    ...p,
  }) as AllocationResponse;

describe('состояние строки сценария', () => {
  it('класс строки главнее отметки', () => {
    expect(scenarioRowState('row-state-no-estimates', true)).toEqual({ key: 'no-estimates', label: 'нет оценок' });
    expect(scenarioRowState('row-state-deficit', true).label).toBe('включено при дефиците');
    expect(scenarioRowState('row-state-in-work', false).label).toBe('уже в работе');
  });
  it('без класса: отмеченная — «включено», прочие — прочерк', () => {
    expect(scenarioRowState('', true)).toEqual({ key: 'included', label: 'включено' });
    expect(scenarioRowState('', false)).toEqual({ key: 'none', label: '—' });
  });
});

describe('часы по ролям', () => {
  const items = [
    alloc({}),
    alloc({ included: false, estimate_analyst_hours: 5, estimate_dev_hours: 5, estimate_qa_hours: 0, estimate_opo_hours: 0 }),
    alloc({ override_estimate_dev_hours: 100 }),
  ];
  it('суммирует все строки и считает отмеченные', () => {
    const t = roleHoursTotals(items, false);
    // Переоценка заменяет оценку целиком: у третьей строки только 100 ч разработки.
    expect(t).toEqual({ analyst: 65, dev: 145, qa: 20, opo: 10, included: 2, total: 240 });
  });
  it('только отмеченные', () => {
    const t = roleHoursTotals(items, false, true);
    expect(t.analyst).toBe(60);
    expect(t.dev).toBe(140);
    expect(t.included).toBe(2);
  });
  it('после отсечки ОПЭ её часы делятся между АН и ПР', () => {
    const t = roleHoursTotals([alloc({})], true);
    expect(t).toMatchObject({ analyst: 65, dev: 45, qa: 20, opo: 0, total: 130 });
  });
});

describe('полоса «план / доступно»', () => {
  it('доступное — на отметке 1/запас ширины', () => {
    const b = capacityBar(425, 520, 1.2);
    expect(b.markerPct).toBeCloseTo(83.33, 1);
    expect(b.fillPct).toBeCloseTo(68.1, 1);
    expect(b.over).toBe(false);
    expect(b.loadPct).toBe(82);
  });
  it('перегруз виден правее отметки, но не шире полосы', () => {
    expect(capacityBar(1085, 1050, 1.2).over).toBe(true);
    expect(capacityBar(1085, 1050, 1.2).loadPct).toBe(103);
    expect(capacityBar(5000, 100, 1.2).fillPct).toBe(100);
  });
  it('без доступного: план есть — полоса целиком, плана нет — пусто', () => {
    expect(capacityBar(73, 0, 1.2)).toEqual({ fillPct: 100, markerPct: null, over: true, loadPct: 0 });
    expect(capacityBar(0, 0, 1.2)).toEqual({ fillPct: 0, markerPct: null, over: false, loadPct: 0 });
  });
});

describe('подписи', () => {
  it('formatHours: целые как есть, дробные до десятых, разряды пробелом', () => {
    expect(formatHours(1900).replace(/\s/g, ' ')).toBe('1 900');
    expect(formatHours(12.34)).toBe('12,3');
    expect(formatHours(-35)).toBe('-35');
  });
  it('roleShortLabel: свои коды по таблице, прочие — две буквы названия', () => {
    expect(roleShortLabel('analyst', 'Аналитик')).toBe('АН');
    expect(roleShortLabel('project_manager', 'Руководитель проектов')).toBe('РП');
    expect(roleShortLabel('designer', 'дизайнер')).toBe('ДИ');
    expect(roleShortLabel('x', null)).toBe('X');
  });
  it('personInitials', () => {
    expect(personInitials('Иванов Сергей')).toBe('ИС');
    expect(personInitials('  ковалёв  дмитрий петрович ')).toBe('КД');
    expect(personInitials('Admin')).toBe('AD');
    expect(personInitials('')).toBe('—');
  });
});

describe('роли, задетые строкой', () => {
  it('анализ (с долей ОПЭ), разработка, тестирование', () => {
    expect(rolesAffectedByAllocation(alloc({}), [])).toEqual(['analyst', 'dev', 'qa']);
  });
  it('исполнитель-РП забирает анализ на свою роль', () => {
    const a = alloc({ assignee_employee_id: 'pm', estimate_qa_hours: 0 });
    expect(rolesAffectedByAllocation(a, [{ employee_id: 'pm', role: 'project_manager' }]))
      .toEqual(['project_manager', 'dev']);
  });
  it('пустая оценка — ничего', () => {
    const a = alloc({ estimate_analyst_hours: 0, estimate_dev_hours: 0, estimate_qa_hours: 0, estimate_opo_hours: 0 });
    expect(rolesAffectedByAllocation(a, undefined)).toEqual([]);
  });
});
