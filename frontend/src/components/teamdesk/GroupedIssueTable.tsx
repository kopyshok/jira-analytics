import { useState } from 'react';
import { Card, Space, Tag, Typography } from 'antd';
import {
  FLAG_LABELS, FLAG_ORDER,
  type DeskDeveloper, type DeskIssue, type FlagCode,
} from '../../api/teamDesk';
import { GroupedIssues } from './GroupedIssues';

const ICON: Record<FlagCode, string> = {
  over: '↑', under: '↓', decomp: '⊞', childgap: '⊟',
  noest: '∅', nospent: '◔', stale: '⏳',
};
const COLOR: Record<FlagCode, string> = {
  over: 'red', under: 'gold', decomp: 'orange', childgap: 'volcano',
  noest: 'default', nospent: 'default', stale: 'purple',
};

interface Props {
  developers: DeskDeveloper[];
  issues: DeskIssue[];
  flagCounts: Partial<Record<FlagCode, number>>;
  overrunPct: number;
  jiraBaseUrl?: string;
}

/** Раскладка «Проблемы вперёд»: лента признаков-фильтров над общим списком. */
export function GroupedIssueTable({
  developers, issues, flagCounts, overrunPct, jiraBaseUrl,
}: Props) {
  const [filter, setFilter] = useState<FlagCode | null>(null);

  return (
    <Space orientation="vertical" size={14} style={{ width: '100%' }}>
      <Card size="small" title="Что требует внимания">
        <Space wrap size={6}>
          {FLAG_ORDER.filter((f) => flagCounts[f]).map((flag) => (
            <Tag
              key={flag}
              color={filter === flag ? 'blue' : COLOR[flag]}
              style={{ cursor: 'pointer' }}
              onClick={() => setFilter(filter === flag ? null : flag)}
            >
              {ICON[flag]} {FLAG_LABELS[flag]} · {flagCounts[flag]}
            </Tag>
          ))}
          {FLAG_ORDER.every((f) => !flagCounts[f]) && (
            <Typography.Text type="secondary">Замечаний нет</Typography.Text>
          )}
        </Space>
      </Card>

      <GroupedIssues
        title="Задачи по разработчикам"
        developers={developers}
        issues={issues}
        overrunPct={overrunPct}
        jiraBaseUrl={jiraBaseUrl}
        scale="centered"
        flagFilter={filter}
        hint={filter ? `отфильтровано: ${FLAG_LABELS[filter]}` : ''}
      />
    </Space>
  );
}
