import { Tag } from 'antd';
import {
  NOTE_TYPE_COLORS, NOTE_TYPE_LABELS, SECTION_LABELS,
} from '../../types/releaseNotes';
import type { ReleaseNote } from '../../types/releaseNotes';
import { DARK_THEME } from '../../utils/constants';
import { useSkin } from '../../contexts/ThemeContext';
import { readablePair } from '../../utils/readableColor';

interface Props {
  note: ReleaseNote;
}

export default function NoteCard({ note }: Props) {
  // В светлом скине метка типа — светлая подложка и тёмный текст того же оттенка:
  // серая «Исправление» иначе не читается.
  const skin = useSkin();
  const typeColor = NOTE_TYPE_COLORS[note.note_type];
  const typePair = skin ? readablePair(typeColor) : null;
  return (
    <div
      style={{
        padding: '12px 16px',
        background: DARK_THEME.darkRows,
        borderRadius: 6,
        borderLeft: `3px solid ${NOTE_TYPE_COLORS[note.note_type]}`,
        marginBottom: 8,
      }}
    >
      <div style={{ marginBottom: 4 }}>
        <Tag
          color={typePair ? undefined : typeColor}
          style={{ marginRight: 8, ...(typePair ? { background: typePair.bg, color: typePair.fg } : {}) }}
        >
          {NOTE_TYPE_LABELS[note.note_type]}
        </Tag>
        <Tag style={{ marginRight: 8 }}>{SECTION_LABELS[note.section]}</Tag>
        <span style={{ fontWeight: 600 }}>{note.title}</span>
      </div>
      <div style={{ color: DARK_THEME.textSecondary, whiteSpace: 'pre-line' }}>
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
