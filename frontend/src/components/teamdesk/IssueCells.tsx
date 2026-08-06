import { Tag, Tooltip, Typography } from 'antd';
import { STATUS_GROUP_LABELS, type StatusGroup } from '../../api/teamDesk';

const GROUP_COLOR: Record<StatusGroup, string> = {
  dev: '#4ba3ff',
  waiting: '#eeb13c',
  todo: '#788799',
  done: '#3ebd85',
  unassigned: '#a78bfa',
};

/** Статус с точкой-меткой: чей сейчас мяч. */
export function StatusTag({ status, group }: { status: string; group: StatusGroup }) {
  return (
    <Tooltip title={STATUS_GROUP_LABELS[group]}>
      <Tag style={{ marginInlineEnd: 0 }}>
        <span
          style={{
            display: 'inline-block', width: 6, height: 6, borderRadius: '50%',
            background: GROUP_COLOR[group], marginRight: 6,
          }}
        />
        {status}
      </Tag>
    </Tooltip>
  );
}

/** Ключ задачи — ссылка в Jira, если известен адрес сервиса. */
export function IssueKey({ issueKey, jiraBaseUrl }: { issueKey: string; jiraBaseUrl?: string }) {
  if (!jiraBaseUrl) return <Typography.Text strong>{issueKey}</Typography.Text>;
  return (
    <Typography.Link
      href={`${jiraBaseUrl}/browse/${issueKey}`}
      target="_blank"
      rel="noreferrer"
      onClick={(e) => e.stopPropagation()}
    >
      {issueKey}
    </Typography.Link>
  );
}
