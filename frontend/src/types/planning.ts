// Планировочные типы для /planning/capacity-preview.
// Формально часть domain-типов, но вынесены в отдельный файл, чтобы
// не раздувать общий api.ts (см. план 2026-04-20-backlog-planning-chain, Task 22).

export interface CapacityPreviewRequest {
  year: number;
  quarter: number;
  backlog_item_ids: string[];
  team_filter?: string[];
}

export interface EmployeeCapacityRow {
  employee_id: string;
  name: string;
  /** Backend-валидированная роль из whitelist {analyst,dev,qa}. Любое другое
   *  значение приходит как строка ("other" или legacy-код) или null, если роль
   *  не задана — такие сотрудники не попадают в capacity_by_role. */
  role: 'analyst' | 'dev' | 'qa' | string | null;
  raw_hours: number;
  mandatory_hours: number;
  absence_hours: number;
  available_hours: number;
  vacation_days: number;
}

export interface CapacityPreviewResponse {
  capacity_by_role: { analyst: number; dev: number; qa: number };
  demand_by_role:   { analyst: number; dev: number; qa: number };
  total_capacity: number;
  total_demand: number;
  gross_hours: number;
  absence_hours: number;
  mandatory_hours: number;
  available_hours: number;
  per_employee: EmployeeCapacityRow[];
}
