import { Tag, Tooltip, Typography } from 'antd';
import {
  STATUS_GROUP_COLOR as GROUP_COLOR, STATUS_GROUP_LABELS, type StatusGroup,
} from '../../api/teamDesk';
import { STATUS_GROUP_TONE } from '../../utils/teamDeskView';

/**
 * Статус с точкой-меткой: чей сейчас мяч. В компактном виде скина — мягкая
 * пилюля цвета группы, без точки.
 */
export function StatusTag({
  status, group, compact = false,
}: { status: string; group: StatusGroup; compact?: boolean }) {
  if (compact) {
    return (
      // Узкая колонка обрезает длинный статус — в подсказке он целиком.
      <Tooltip title={`${status} · ${STATUS_GROUP_LABELS[group]}`}>
        <span className={`wr-pill is-sm is-${STATUS_GROUP_TONE[group]} tdc-status`}>{status}</span>
      </Tooltip>
    );
  }
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
export function IssueKey({
  issueKey, jiraBaseUrl, style,
}: { issueKey: string; jiraBaseUrl?: string; style?: React.CSSProperties }) {
  if (!jiraBaseUrl) return <Typography.Text strong style={style}>{issueKey}</Typography.Text>;
  return (
    <Typography.Link
      href={`${jiraBaseUrl}/browse/${issueKey}`}
      target="_blank"
      rel="noreferrer"
      onClick={(e) => e.stopPropagation()}
      style={style}
    >
      {issueKey}
    </Typography.Link>
  );
}
