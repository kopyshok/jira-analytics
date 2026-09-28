import { describe, expect, it } from 'vitest';
import { fmtHours, itemsForRow, overuseCount, overuseLabel, resolvedOverrideKeys } from './normedReserve';
import type { OtherTeamWorkOut, ReserveOut } from '../api/resourcePlanning';

const otherTeamWork: OtherTeamWorkOut[] = [
  {
    backlog_item_id: 'bi1', issue_key: 'ERP-1', title: 'Задача 1', team: 'Продажи',
    role: 'dev', hours: 100, work_type_id: 'wt1', is_manual: false,
  },
  {
    backlog_item_id: 'bi2', issue_key: 'ERP-2', title: 'Задача 2', team: 'Продажи',
    role: 'dev', hours: 80, work_type_id: 'wt1', is_manual: true,
  },
  {
    backlog_item_id: 'bi3', issue_key: 'ERP-3', title: 'Задача 3', team: 'Продажи',
    role: 'dev', hours: 15, work_type_id: 'wt2', is_manual: false,
  },
  {
    backlog_item_id: 'bi4', issue_key: 'ERP-4', title: 'Задача 4', team: 'Продажи',
    role: 'analyst', hours: 40, work_type_id: 'wt1', is_manual: false,
  },
];

const reserve: ReserveOut = {
  team: 'ERP',
  scenario_name: 'Сценарий Q1',
  roles: [
    {
      role: 'dev',
      role_label: 'Разработчик',
      rows: [
        {
          work_type_id: 'wt1', label: 'Технические задачи',
          planned_hours: 102, blocked_hours: 0, other_teams_hours: 180,
          remaining_hours: 0, overuse_hours: 78,
        },
        {
          work_type_id: 'wt2', label: 'Орг. вопросы',
          planned_hours: 50, blocked_hours: 0, other_teams_hours: 0,
          remaining_hours: 49.8, overuse_hours: 0.2,
        },
      ],
    },
  ],
  other_team_work: otherTeamWork,
  work_types: [],
};

describe('overuseCount', () => {
  it('нет запаса — 0', () => {
    expect(overuseCount(null)).toBe(0);
    expect(overuseCount(undefined)).toBe(0);
  });
  it('считает строки с перерасходом больше 0,5 ч', () => {
    expect(overuseCount(reserve)).toBe(1);
  });
});

describe('overuseLabel', () => {
  it('нет перерасхода — null', () => {
    expect(overuseLabel(null)).toBeNull();
    expect(overuseLabel({ ...reserve, roles: [] })).toBeNull();
  });
  it('склоняет «вид» по числу строк с перерасходом', () => {
    expect(overuseLabel(reserve)).toBe('перерасход: 1 вид работ');
    const two: ReserveOut = {
      ...reserve,
      roles: [
        { ...reserve.roles[0] },
        { ...reserve.roles[0], role: 'analyst', role_label: 'Аналитик' },
      ],
    };
    expect(overuseLabel(two)).toBe('перерасход: 2 вида работ');
  });
});

describe('fmtHours', () => {
  it('округляет до десятых и подписывает часы', () => {
    expect(fmtHours(101.6)).toBe('101,6 ч');
    expect(fmtHours(0)).toBe('0 ч');
  });
});

describe('itemsForRow', () => {
  it('берёт задачи только этой роли и вида работ', () => {
    expect(itemsForRow(reserve, 'dev', 'wt1')).toEqual([otherTeamWork[0], otherTeamWork[1]]);
    expect(itemsForRow(reserve, 'dev', 'wt2')).toEqual([otherTeamWork[2]]);
  });
  it('не путает роли с одинаковым видом работ', () => {
    expect(itemsForRow(reserve, 'analyst', 'wt1')).toEqual([otherTeamWork[3]]);
  });
  it('нет совпадений — пустой список', () => {
    expect(itemsForRow(reserve, 'qa', 'wt1')).toEqual([]);
  });
});

describe('resolvedOverrideKeys', () => {
  it('подтверждённая подмена — ключ попадает в список', () => {
    // bi2 — ручной выбор wt1, локальная подмена тоже wt1 (сервер подтвердил).
    expect(resolvedOverrideKeys(otherTeamWork, { bi2: 'wt1' })).toEqual(['bi2']);
  });

  it('подмена ещё не подтверждена — ключ остаётся', () => {
    expect(resolvedOverrideKeys(otherTeamWork, { bi2: 'wt2' })).toEqual([]);
  });

  it('задача с двумя ролями — одно совпадение снимает подмену независимо от строки', () => {
    // Одна и та же задача (bi5) исполняется двумя ролями — сервер хранит один вид работ на задачу.
    const twoRoles: OtherTeamWorkOut[] = [
      { backlog_item_id: 'bi5', issue_key: 'ERP-5', title: 'Задача 5', team: 'Продажи', role: 'dev', hours: 10, work_type_id: 'wt1', is_manual: true },
      { backlog_item_id: 'bi5', issue_key: 'ERP-5', title: 'Задача 5', team: 'Продажи', role: 'analyst', hours: 5, work_type_id: 'wt1', is_manual: true },
    ];
    expect(resolvedOverrideKeys(twoRoles, { bi5: 'wt1' })).toEqual(['bi5']);
  });

  it('задачи без подмены в списке нет', () => {
    expect(resolvedOverrideKeys(otherTeamWork, {})).toEqual([]);
  });

  it('сброс на «Технические задачи» (null) — подтверждается когда is_manual снят', () => {
    const cleared: OtherTeamWorkOut[] = [
      { backlog_item_id: 'bi2', issue_key: 'ERP-2', title: 'Задача 2', team: 'Продажи', role: 'dev', hours: 80, work_type_id: 'wt1', is_manual: false },
    ];
    expect(resolvedOverrideKeys(cleared, { bi2: null })).toEqual(['bi2']);
  });
});
