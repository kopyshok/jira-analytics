import React from 'react';
import { Card, Empty } from 'antd';
import { useNavigate } from 'react-router';
import type { EmployeeBreakdown } from '../../../types/projects';
import { DARK_THEME } from '../../../utils/constants';

interface Props {
  employees: EmployeeBreakdown[];
  projectKey: string;
}

const AVATAR_COLORS = ['#378ADD', '#1D9E75', '#EF9F27', '#7F77DD', 'var(--text-muted, #7e94b8)', 'var(--text-muted, #7e94b8)', 'var(--text-muted, #7e94b8)'];

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  const first = parts[0]?.[0] ?? '';
  const second = parts[1]?.[0] ?? '';
  return (first + second).toUpperCase();
}

export const ProjectEmployeesCard: React.FC<Props> = ({ employees, projectKey }) => {
  const navigate = useNavigate();

  if (!employees || employees.length === 0) {
    return (
      <Card
        size="small"
        title={<span style={{ color: 'var(--text-2, #cfd8e5)', fontSize: 13 }}>Участники</span>}
        style={{ background: DARK_THEME.cardBg, border: '1px solid rgba(255,255,255,0.06)' }}
        styles={{ header: { borderColor: 'rgba(255,255,255,0.06)' }, body: { padding: 12 } }}
      >
        <Empty description="Нет данных" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </Card>
    );
  }

  const maxHours = Math.max(...employees.map((e) => e.hours));

  return (
    <Card
      size="small"
      title={<span style={{ color: 'var(--text-2, #cfd8e5)', fontSize: 13 }}>Участники</span>}
      style={{ background: DARK_THEME.cardBg, border: '1px solid rgba(255,255,255,0.06)' }}
      styles={{ header: { borderColor: 'rgba(255,255,255,0.06)' }, body: { padding: 12 } }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {employees.map((emp, i) => {
          const openEmployee = () =>
            navigate(`/analytics?employee=${emp.employee_id}&project=${projectKey}`);
          return (
            <div
              key={emp.employee_id}
              role="button"
              tabIndex={0}
              style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}
              onClick={openEmployee}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  openEmployee();
                }
              }}
            >
              <div
                style={{
                  width: 28,
                  height: 28,
                  borderRadius: '50%',
                  background: AVATAR_COLORS[i % AVATAR_COLORS.length],
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 11,
                  fontWeight: 700,
                  color: DARK_THEME.textPrimary,
                  flexShrink: 0,
                }}
              >
                {initials(emp.name)}
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 3 }}>
                  <span style={{ color: 'var(--text-2, #cfd8e5)', fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {emp.name}
                  </span>
                  <span style={{ color: DARK_THEME.textMuted, fontSize: 11, whiteSpace: 'nowrap', marginLeft: 8 }}>
                    {Math.round(emp.hours)} ч · {emp.pct}%
                  </span>
                </div>
                <div style={{ height: 4, background: 'rgba(255,255,255,0.08)', borderRadius: 2, overflow: 'hidden' }}>
                  <div
                    style={{
                      height: '100%',
                      width: `${maxHours > 0 ? (emp.hours / maxHours) * 100 : 0}%`,
                      background: AVATAR_COLORS[i % AVATAR_COLORS.length],
                      borderRadius: 2,
                    }}
                  />
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </Card>
  );
};
