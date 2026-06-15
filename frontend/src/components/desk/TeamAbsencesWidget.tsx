import { List, Tag } from 'antd';
import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { fmtRange } from './format';
import type { TeamAbsence, TeamAbsencesData } from '../../types/desk';

export default function TeamAbsencesWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<TeamAbsencesData>(token, 'team_absences');
  const absences = data?.absences ?? [];

  // Группировка по сотруднику.
  const byEmp = new Map<string, TeamAbsence[]>();
  for (const a of absences) {
    const arr = byEmp.get(a.employee_name) ?? [];
    arr.push(a);
    byEmp.set(a.employee_name, arr);
  }
  const groups = [...byEmp.entries()];

  return (
    <WidgetShell
      title={title}
      isLoading={isLoading}
      isError={isError}
      isEmpty={groups.length === 0}
      emptyText="Отсутствий нет"
    >
      <List
        size="small"
        dataSource={groups}
        renderItem={([name, items]) => (
          <List.Item>
            <List.Item.Meta
              title={name}
              description={items.map((a, i) => (
                <div key={i}>
                  <Tag color={a.color ?? undefined}>{a.reason_label}</Tag>
                  {fmtRange(a.start_date, a.end_date)}
                </div>
              ))}
            />
          </List.Item>
        )}
      />
    </WidgetShell>
  );
}
