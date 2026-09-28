import { describe, expect, it } from 'vitest';
import type { AllocationResponse } from '../types/api';
import { demandByEmployee } from './planning';

const alloc = (p: Partial<AllocationResponse>): AllocationResponse =>
  ({
    included: true,
    estimate_analyst_hours: 60,
    estimate_dev_hours: 40,
    estimate_qa_hours: 20,
    estimate_opo_hours: 0,
    override_estimate_analyst_hours: null,
    override_estimate_dev_hours: null,
    override_estimate_qa_hours: null,
    override_estimate_opo_hours: null,
    opo_analyst_ratio: 0.5,
    assignee_employee_id: null,
    assignee_display_name: null,
    developer_employee_id: null,
    ...p,
  }) as AllocationResponse;

const team = [
  { employee_id: 'an', role: 'analyst', display_name: 'Фокеева Наталья' },
  { employee_id: 'dev1', role: 'dev', display_name: 'Шутов Сергей' },
  { employee_id: 'dev2', role: 'dev', display_name: 'Пряничников Алексей' },
];

describe('demandByEmployee', () => {
  it('разработчик из колонки получает часы разработки, аналитик — анализа', () => {
    const d = demandByEmployee(
      [alloc({ assignee_employee_id: 'an', developer_employee_id: 'dev1' })],
      team,
    );
    expect(d).toEqual({ an: 60, dev1: 40 });
  });

  it('колонка заполнена — исполнитель-разработчик идёт на анализ', () => {
    const d = demandByEmployee(
      [alloc({ assignee_employee_id: 'dev2', developer_employee_id: 'dev1' })],
      team,
    );
    expect(d).toEqual({ dev2: 60, dev1: 40 });
  });

  it('один и тот же человек в обеих колонках — только разработка', () => {
    const d = demandByEmployee(
      [alloc({ assignee_employee_id: 'dev1', developer_employee_id: 'dev1' })],
      team,
    );
    expect(d).toEqual({ dev1: 40 });
  });

  it('колонка пустая — как раньше: часы по роли исполнителя', () => {
    const d = demandByEmployee([alloc({ assignee_employee_id: 'dev1' })], team);
    expect(d).toEqual({ dev1: 40 });
  });

  it('не включённые строки не считаются', () => {
    const d = demandByEmployee(
      [alloc({ included: false, assignee_employee_id: 'an', developer_employee_id: 'dev1' })],
      team,
    );
    expect(d).toEqual({});
  });
});
