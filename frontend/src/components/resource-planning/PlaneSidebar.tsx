import { useState } from 'react';
import { Checkbox, Input } from 'antd';
import type { EmployeeResponse } from '../../types/api';
import css from './PlaneGantt.module.css';

export type PlaneFilters = {
  projects: string[];
  employees: string[];
  roles: string[];
  status: string[];
};

type ProjectEntry = { key: string; count: number };

type Props = {
  employees: EmployeeResponse[];
  projects: ProjectEntry[];
  filters: PlaneFilters;
  quarter: string;
  year: number;
  onChange: (next: PlaneFilters) => void;
};

type GroupKey = 'project' | 'employee' | 'role' | 'period' | 'status';

const ROLE_OPTIONS: { value: string; label: string; chipClass: string }[] = [
  { value: 'analyst', label: 'Аналитик', chipClass: css.chipAnalyst },
  { value: 'dev', label: 'Разработчик', chipClass: css.chipDev },
  { value: 'qa', label: 'Тестировщик', chipClass: css.chipQa },
  { value: 'opo', label: 'ОПЭ', chipClass: css.chipOpo },
];

const STATUS_OPTIONS: { value: string; label: string; chipClass: string }[] = [
  { value: 'draft', label: 'Черновик', chipClass: css.chipDraft },
  { value: 'approved', label: 'Утверждён', chipClass: css.chipApproved },
  { value: 'active', label: 'В работе', chipClass: css.chipActive },
];

function toggleSet(arr: string[], value: string): string[] {
  return arr.includes(value) ? arr.filter(x => x !== value) : [...arr, value];
}

export default function PlaneSidebar({ employees, projects, filters, quarter, year, onChange }: Props) {
  const [openGroups, setOpenGroups] = useState<Set<GroupKey>>(
    new Set(['project', 'employee', 'role', 'period', 'status']),
  );
  const [empSearch, setEmpSearch] = useState('');

  const toggleGroup = (key: GroupKey) => {
    setOpenGroups(prev => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const isOpen = (key: GroupKey) => openGroups.has(key);

  const filteredEmployees = empSearch.trim()
    ? employees.filter(e => e.display_name.toLowerCase().includes(empSearch.toLowerCase()))
    : employees;

  const quarterWeeks = 13;

  return (
    <div className={css.sidebar}>
      {/* Проект */}
      <div className={css.filterGroup}>
        <div className={css.filterGroupHeader} onClick={() => toggleGroup('project')}>
          <span>Проект</span>
          <span className={`${css.filterGroupCaret}${isOpen('project') ? ` ${css.open}` : ''}`}>▶</span>
        </div>
        {isOpen('project') && (
          <div className={css.filterGroupBody}>
            {projects.length === 0 && (
              <div className={css.filterItem} style={{ color: 'var(--pl-text-dim)', cursor: 'default' }}>
                Нет данных
              </div>
            )}
            {projects.map(p => (
              <label key={p.key} className={css.filterItem}>
                <Checkbox
                  checked={filters.projects.includes(p.key)}
                  onChange={() => onChange({ ...filters, projects: toggleSet(filters.projects, p.key) })}
                />
                <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {p.key}
                </span>
                <span className={css.filterItemCount}>{p.count}</span>
              </label>
            ))}
          </div>
        )}
      </div>

      {/* Сотрудник */}
      <div className={css.filterGroup}>
        <div className={css.filterGroupHeader} onClick={() => toggleGroup('employee')}>
          <span>Сотрудник</span>
          <span className={`${css.filterGroupCaret}${isOpen('employee') ? ` ${css.open}` : ''}`}>▶</span>
        </div>
        {isOpen('employee') && (
          <div className={css.filterGroupBody}>
            <div className={css.employeeSearch}>
              <Input
                size="small"
                placeholder="Поиск…"
                value={empSearch}
                onChange={e => setEmpSearch(e.target.value)}
                allowClear
              />
            </div>
            <div style={{ maxHeight: 200, overflowY: 'auto' }}>
              {filteredEmployees.map(e => (
                <label key={e.id} className={css.filterItem}>
                  <Checkbox
                    checked={filters.employees.includes(e.id)}
                    onChange={() => onChange({ ...filters, employees: toggleSet(filters.employees, e.id) })}
                  />
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {e.display_name}
                  </span>
                </label>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Роль */}
      <div className={css.filterGroup}>
        <div className={css.filterGroupHeader} onClick={() => toggleGroup('role')}>
          <span>Роль</span>
          <span className={`${css.filterGroupCaret}${isOpen('role') ? ` ${css.open}` : ''}`}>▶</span>
        </div>
        {isOpen('role') && (
          <div className={css.filterGroupBody}>
            {ROLE_OPTIONS.map(r => (
              <label key={r.value} className={css.filterItem}>
                <Checkbox
                  checked={filters.roles.includes(r.value)}
                  onChange={() => onChange({ ...filters, roles: toggleSet(filters.roles, r.value) })}
                />
                <span className={`${css.chip} ${r.chipClass}`}>{r.label}</span>
              </label>
            ))}
          </div>
        )}
      </div>

      {/* Период */}
      <div className={css.filterGroup}>
        <div className={css.filterGroupHeader} onClick={() => toggleGroup('period')}>
          <span>Период</span>
          <span className={`${css.filterGroupCaret}${isOpen('period') ? ` ${css.open}` : ''}`}>▶</span>
        </div>
        {isOpen('period') && (
          <div className={css.filterGroupBody}>
            <div className={css.chipsRow}>
              <span className={`${css.chip} ${css.chipActive}`}>
                {quarter} {year} · {quarterWeeks} нед.
              </span>
            </div>
          </div>
        )}
      </div>

      {/* Статус */}
      <div className={css.filterGroup}>
        <div className={css.filterGroupHeader} onClick={() => toggleGroup('status')}>
          <span>Статус</span>
          <span className={`${css.filterGroupCaret}${isOpen('status') ? ` ${css.open}` : ''}`}>▶</span>
        </div>
        {isOpen('status') && (
          <div className={css.filterGroupBody}>
            <div className={css.chipsRow}>
              {STATUS_OPTIONS.map(s => (
                <span key={s.value} className={`${css.chip} ${s.chipClass}`}>{s.label}</span>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className={css.sidebarFooter}>
        <button
          type="button"
          className={css.resetLink}
          onClick={() => onChange({ projects: [], employees: [], roles: [], status: [] })}
        >
          Сбросить все фильтры
        </button>
      </div>
    </div>
  );
}
