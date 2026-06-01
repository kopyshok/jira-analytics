import { useState } from 'react';
import { Checkbox, Collapse, Empty, Spin } from 'antd';
import { useAllReleaseNotes } from '../../hooks/useReleaseNotes';
import NoteCard from './NoteCard';

export default function AllVersionsView() {
  const { data, isLoading } = useAllReleaseNotes();
  const [hideFixes, setHideFixes] = useState(false);

  if (isLoading) {
    return (
      <div style={{ textAlign: 'center', padding: 32 }}>
        <Spin />
      </div>
    );
  }
  if (!data || data.feeds.length === 0) {
    return <Empty description="Версий пока нет" />;
  }

  return (
    <div>
      <Checkbox
        checked={hideFixes}
        onChange={(e) => setHideFixes(e.target.checked)}
        style={{ marginBottom: 16 }}
      >
        Скрыть исправления
      </Checkbox>
      <Collapse
        defaultActiveKey={data.feeds.length > 0 ? [data.feeds[0].version] : []}
        items={data.feeds.map((feed) => {
          const visible = hideFixes
            ? feed.notes.filter((n) => n.note_type !== 'fix')
            : feed.notes;
          return {
            key: feed.version,
            label: feed.version,
            children: visible.length === 0
              ? <Empty description="Здесь нет записей с учётом фильтра" />
              : visible.map((n) => <NoteCard key={n.id} note={n} />),
          };
        })}
      />
    </div>
  );
}
