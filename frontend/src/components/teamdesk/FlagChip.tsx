import { useState } from 'react';
import { Dropdown, Input, Modal, Tag, Tooltip } from 'antd';
import { FLAG_LABELS, type FlagCode, type ReviewedMark } from '../../api/teamDesk';
import { useMarkFlag, useUnmarkFlag } from '../../hooks/useTeamDesk';

const ICON: Record<FlagCode, string> = {
  over: '↑', under: '↓', decomp: '⊞', childgap: '⊟',
  noest: '∅', nospent: '◔', stale: '⏳',
};

const COLOR: Record<FlagCode, string> = {
  over: 'red', under: 'gold', decomp: 'orange', childgap: 'volcano',
  noest: 'default', nospent: 'default', stale: 'purple',
};

interface Props {
  issueId: string;
  flag: FlagCode;
  signature: string;
  reviewed?: ReviewedMark;
  count?: number;
  /** Показывать подпись рядом со значком */
  withLabel?: boolean;
}

/**
 * Значок признака. Клик открывает действие «Просмотрено» — признак перестаёт
 * считаться проблемой, пока не изменится причина.
 */
export function FlagChip({ issueId, flag, signature, reviewed, count, withLabel }: Props) {
  const [open, setOpen] = useState(false);
  const [comment, setComment] = useState('');
  const mark = useMarkFlag();
  const unmark = useUnmarkFlag();

  const label = FLAG_LABELS[flag];
  const title = reviewed
    ? `${label} · просмотрено ${new Date(reviewed.marked_at).toLocaleDateString('ru')}${
        reviewed.comment ? ` · ${reviewed.comment}` : ''
      }`
    : label;

  const items = reviewed
    ? [{ key: 'unmark', label: 'Вернуть в проблемные' }]
    : [{ key: 'mark', label: 'Просмотрено' }];

  return (
    <>
      <Dropdown
        menu={{
          items,
          onClick: ({ key }) => {
            if (key === 'unmark') unmark.mutate({ issueId, flag });
            else setOpen(true);
          },
        }}
        trigger={['click']}
      >
        <Tooltip title={title}>
          <Tag
            color={reviewed ? 'default' : COLOR[flag]}
            style={{ cursor: 'pointer', opacity: reviewed ? 0.45 : 1, marginInlineEnd: 4 }}
          >
            {ICON[flag]}
            {withLabel ? ` ${label}` : ''}
            {count != null ? ` ${count}` : ''}
          </Tag>
        </Tooltip>
      </Dropdown>

      <Modal
        title={`Просмотрено: ${label}`}
        open={open}
        okText="Отметить"
        cancelText="Отмена"
        onCancel={() => setOpen(false)}
        onOk={() => {
          mark.mutate({ issueId, flag, signature, comment: comment || undefined });
          setComment('');
          setOpen(false);
        }}
      >
        <p style={{ opacity: 0.7 }}>
          Признак перестанет считаться проблемой. Если причина изменится — задача сменит
          статус, вырастет факт или поменяется оценка — он вернётся.
        </p>
        <Input.TextArea
          rows={2}
          placeholder="Комментарий (необязательно)"
          value={comment}
          onChange={(e) => setComment(e.target.value)}
        />
      </Modal>
    </>
  );
}

/** Список значков задачи: непросмотренные + просмотренные (приглушённо). */
export function FlagList({
  issueId,
  flags,
  signatures,
  reviewed,
}: {
  issueId: string;
  flags: FlagCode[];
  signatures: Partial<Record<FlagCode, string>>;
  reviewed: ReviewedMark[];
}) {
  const reviewedMap = new Map(reviewed.map((r) => [r.flag, r]));
  const shown = new Set(flags);
  const extra = reviewed.filter((r) => !shown.has(r.flag));

  if (flags.length === 0 && extra.length === 0) {
    return <span style={{ opacity: 0.35 }}>—</span>;
  }
  return (
    <span>
      {flags.map((flag) => (
        <FlagChip
          key={flag}
          issueId={issueId}
          flag={flag}
          signature={signatures[flag] ?? ''}
          reviewed={reviewedMap.get(flag)}
        />
      ))}
      {extra.map((r) => (
        <FlagChip
          key={`r-${r.flag}`}
          issueId={issueId}
          flag={r.flag}
          signature={signatures[r.flag] ?? ''}
          reviewed={r}
        />
      ))}
    </span>
  );
}
