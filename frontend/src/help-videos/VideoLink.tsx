import { useState } from 'react';
import { PlayCircleFilled } from '@ant-design/icons';
import { DARK_THEME } from '../utils/constants';
import { VIDEOS } from './videos';
import VideoModal from './VideoModal';

interface Props {
  id: string;
  /** Текст ссылки из markdown — на случай, если видео с таким id не найдено в реестре. */
  fallback?: string;
}

/** Карточка с обложкой ролика в тексте справки; клик открывает VideoModal. */
export default function VideoLink({ id, fallback }: Props) {
  const [open, setOpen] = useState(false);
  const video = VIDEOS[id];

  if (!video) return <>{fallback ?? id}</>;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={`Смотреть видео: ${video.title}`}
        style={{
          display: 'inline-flex', flexDirection: 'column', width: 260, padding: 0,
          border: `1px solid ${DARK_THEME.border}`, borderRadius: 8, overflow: 'hidden',
          background: 'none', cursor: 'pointer', textAlign: 'left', font: 'inherit',
        }}
      >
        <span style={{ position: 'relative', display: 'block', width: '100%', aspectRatio: '16 / 9' }}>
          <img
            src={video.poster} alt=""
            style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
          />
          <PlayCircleFilled style={{
            position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
            fontSize: 40, color: '#fff', filter: 'drop-shadow(0 1px 4px rgba(0,0,0,0.6))',
          }}
          />
        </span>
        <span style={{ padding: '8px 10px', fontSize: 13, color: DARK_THEME.textPrimary }}>{video.title}</span>
      </button>
      <VideoModal id={open ? id : null} onClose={() => setOpen(false)} />
    </>
  );
}
