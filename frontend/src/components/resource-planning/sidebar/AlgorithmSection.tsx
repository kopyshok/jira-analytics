import type { ReactNode } from 'react';
import { Collapse, Typography } from 'antd';

interface Props {
  log: string[];
  collapsed: boolean;
  onToggleCollapse: () => void;
}

/** Строки-подпункты приходят с префиксом «  · ». Они не получают своего номера
 *  в нумерованном списке, а рендерятся как отступленные пояснения. */
function renderLog(log: string[]) {
  const nodes: ReactNode[] = [];
  let idx = 1;
  for (let i = 0; i < log.length; i++) {
    const line = log[i];
    if (line.startsWith('  ·') || line.startsWith('  ·')) {
      // sub-bullet — отступ относительно последнего пункта
      nodes.push(
        <div
          key={`s-${i}`}
          style={{
            fontSize: 12,
            color: 'var(--text-muted, #8ab0d8)',
            marginLeft: 16,
            marginBottom: 2,
            lineHeight: 1.45,
          }}
        >
          {line.replace(/^\s*·\s*/, '· ')}
        </div>
      );
    } else {
      nodes.push(
        <div
          key={`n-${i}`}
          style={{
            fontSize: 12,
            color: 'var(--text-2, #cfe1f5)',
            marginBottom: 2,
            lineHeight: 1.45,
          }}
        >
          <span style={{ color: 'var(--text-muted, #7a9ab8)', marginRight: 6 }}>{idx}.</span>
          {line}
        </div>
      );
      idx += 1;
    }
  }
  return nodes;
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
          : <div style={{ margin: 0 }}>{renderLog(log)}</div>,
      }]}
    />
  );
}
