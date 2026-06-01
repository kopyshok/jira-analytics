import { Modal, Button, Collapse, Space, Empty } from 'antd';
import type { ReactNode } from 'react';
import NoteCard from './NoteCard';
import type { VersionFeed, ReleaseNote } from '../../types/releaseNotes';

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
          : `Что нового (${feeds.length} версий)`
      }
      footer={footer}
    >
      <Space direction="vertical" size={16} style={{ width: '100%' }}>
        {feeds.map((feed) => {
          const groups = groupByType(feed.notes);
          return (
            <div key={feed.version}>
              {feeds.length > 1 && (
                <h3 style={{ marginTop: 0, marginBottom: 12 }}>{feed.version}</h3>
              )}
              {groups.new.length > 0 && (
                <section style={{ marginBottom: 16 }}>
                  <h4 style={{ color: '#52c41a', marginBottom: 8 }}>Новое</h4>
                  {groups.new.map((n) => <NoteCard key={n.id} note={n} />)}
                </section>
              )}
              {groups.improvement.length > 0 && (
                <section style={{ marginBottom: 16 }}>
                  <h4 style={{ color: '#1677ff', marginBottom: 8 }}>Улучшения</h4>
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
            <span style={{ color: '#8c8c8c' }}>
              Исправления ({notes.length})
            </span>
          ),
          children: notes.map((n) => <NoteCard key={n.id} note={n} />),
        },
      ]}
    />
  );
}
