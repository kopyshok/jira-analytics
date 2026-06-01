import { Tag } from 'antd';
import {
  NOTE_TYPE_COLORS, NOTE_TYPE_LABELS, SECTION_LABELS,
} from '../../types/releaseNotes';
import type { ReleaseNote } from '../../types/releaseNotes';

interface Props {
  note: ReleaseNote;
}

export default function NoteCard({ note }: Props) {
  return (
    <div
      style={{
        padding: '12px 16px',
        background: 'rgba(255,255,255,0.03)',
        borderRadius: 6,
        borderLeft: `3px solid ${NOTE_TYPE_COLORS[note.note_type]}`,
        marginBottom: 8,
      }}
    >
      <div style={{ marginBottom: 4 }}>
        <Tag color={NOTE_TYPE_COLORS[note.note_type]} style={{ marginRight: 8 }}>
          {NOTE_TYPE_LABELS[note.note_type]}
        </Tag>
        <Tag style={{ marginRight: 8 }}>{SECTION_LABELS[note.section]}</Tag>
        <span style={{ fontWeight: 600 }}>{note.title}</span>
      </div>
      <div style={{ color: 'rgba(255,255,255,0.65)', whiteSpace: 'pre-line' }}>
        {note.description}
      </div>
      {note.help_link && (
        <div style={{ marginTop: 4 }}>
          <a href={note.help_link} target="_blank" rel="noreferrer">
            Подробнее в справке →
          </a>
        </div>
      )}
    </div>
  );
}
