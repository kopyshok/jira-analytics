import { Collapse, Typography } from 'antd';

interface Props {
  log: string[];
  collapsed: boolean;
  onToggleCollapse: () => void;
}

export default function AlgorithmSection({ log, collapsed, onToggleCollapse }: Props) {
  return (
    <Collapse
      ghost
      activeKey={collapsed ? [] : ['1']}
      onChange={onToggleCollapse}
      items={[{
        key: '1',
        label: 'Откуда дата старта',
        children: log.length === 0
          ? <Typography.Text type="secondary">Нет данных</Typography.Text>
          : (
            <ol style={{ margin: 0, paddingLeft: 20 }}>
              {log.map((item, i) => (
                <li key={i} style={{ fontSize: 12, color: '#cfe1f5', marginBottom: 2 }}>{item}</li>
              ))}
            </ol>
          ),
      }]}
    />
  );
}
