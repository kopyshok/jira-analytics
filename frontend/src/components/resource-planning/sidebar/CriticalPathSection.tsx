import { Alert, Collapse, Typography } from 'antd';
import type { AssignmentOut } from '../../../api/resourcePlanning';

interface Props {
  assignment: AssignmentOut;
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export default function CriticalPathSection({ assignment, collapsed, onToggleCollapse }: Props) {
  const slack = assignment.slack_days ?? 0;

  return (
    <Collapse
      ghost
      activeKey={collapsed ? [] : ['1']}
      onChange={onToggleCollapse}
      items={[{
        key: '1',
        label: 'Критический путь',
        children: assignment.is_on_critical_path
          ? (
            <Alert
              type="error"
              showIcon
              title="Фаза на критическом пути."
              description={`Резерв: ${slack} дней. Сдвиг сорвёт срок проекта.`}
            />
          )
          : (
            <Typography.Text type="success">
              Не на критическом пути. Резерв: {slack} дней.
            </Typography.Text>
          ),
      }]}
    />
  );
}
