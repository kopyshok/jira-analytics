import { Modal, Button, Collapse, Space, Empty } from 'antd';
import type { ReactNode } from 'react';
import NoteCard from './NoteCard';
import type { VersionFeed, ReleaseNote } from '../../types/releaseNotes';
import { DARK_THEME } from '../../utils/constants';
import { plural } from '../../utils/plural';

/** Заголовок группы заметок: текст основным цветом темы, смысловой цвет — только у метки. */
function GroupTitle({ color, children }: { color: string; children: ReactNode }) {
  return (
    <h4 style={{ color: DARK_THEME.textPrimary, marginBottom: 8, display: 'flex', alignItems: 'center', gap: 8 }}>
      <span aria-hidden style={{ width: 8, height: 8, borderRadius: '50%', background: color }} />
      {children}
    </h4>
  );
}

interface Props {
  open: boolean;
  feeds: VersionFeed[];
  onClose: () => void;
  onMarkSeen: (latestVersion: string) => void;
  onShowAllVersions?: () => void;
}

function groupByType(notes: ReleaseNote[]) {
  return {
    new: notes.filter((n) => n.note_type === 'new'),
    improvement: notes.filter((n) => n.note_type === 'improvement'),
    fix: notes.filter((n) => n.note_type === 'fix'),
  };
}

export default function WhatsNewModal({
  open, feeds, onClose, onMarkSeen, onShowAllVersions,
}: Props) {
  // feeds приходит уже отсортированный по убыванию версии (newest first).
  const latestVersion = feeds[0]?.version ?? '';

  const handleOk = () => {
    if (latestVersion) onMarkSeen(latestVersion);
    onClose();
  };

  if (feeds.length === 0) {
    return (
      <Modal open={open} onCancel={onClose} footer={null} title="Что нового">
        <Empty description="Пока ничего нового" />
      </Modal>
    );
  }

  const footer: ReactNode[] = [];
  if (onShowAllVersions) {
    footer.push(
      <Button key="all" type="link" onClick={onShowAllVersions}>
        Все версии
      </Button>,
    );
  }
  footer.push(
    <Button key="ok" type="primary" onClick={handleOk}>
      Понятно
    </Button>,
  );

  return (
    <Modal
      open={open}
      onCancel={onClose}
      width={720}
      title={
        feeds.length === 1
          ? `Что нового в ${feeds[0].version}`
          : `Что нового (${feeds.length} ${plural(feeds.length, 'версия', 'версии', 'версий')})`
      }
      footer={footer}
    >
      <Space orientation="vertical" size={16} style={{ width: '100%' }}>
        {feeds.map((feed) => {
          const groups = groupByType(feed.notes);
          return (
            <div key={feed.version}>
              {feeds.length > 1 && (
                <h3 style={{ marginTop: 0, marginBottom: 12 }}>{feed.version}</h3>
              )}
              {groups.new.length > 0 && (
                <section style={{ marginBottom: 16 }}>
                  <GroupTitle color="#52c41a">Новое</GroupTitle>
                  {groups.new.map((n) => <NoteCard key={n.id} note={n} />)}
                </section>
              )}
              {groups.improvement.length > 0 && (
                <section style={{ marginBottom: 16 }}>
                  <GroupTitle color="#1677ff">Улучшения</GroupTitle>
                  {groups.improvement.map((n) => <NoteCard key={n.id} note={n} />)}
                </section>
              )}
              {groups.fix.length > 0 && (
                <FixesSection notes={groups.fix} />
              )}
            </div>
          );
        })}
      </Space>
    </Modal>
  );
}

function FixesSection({ notes }: { notes: ReleaseNote[] }) {
  return (
    <Collapse
      ghost
      items={[
        {
          key: 'fixes',
          label: (
            <span style={{ color: DARK_THEME.textMuted }}>
              Исправления ({notes.length})
            </span>
          ),
          children: notes.map((n) => <NoteCard key={n.id} note={n} />),
        },
      ]}
    />
  );
}
