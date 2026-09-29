import { useState } from 'react';
import { Modal } from 'antd';
import { VIDEOS } from './videos';

interface Props {
  id: string | null;
  onClose: () => void;
}

/**
 * Окно с роликом-инструкцией почти на весь экран. Неизвестный id — ничего не показывает.
 * После закрытия заголовок и ролик остаются до конца анимации исчезновения (afterClose),
 * иначе окно пустеет прямо во время затухания. При «уменьшить движение» ролик не стартует сам.
 */
export default function VideoModal({ id, onClose }: Props) {
  const [shownId, setShownId] = useState(id);
  if (id !== null && id !== shownId) setShownId(id);
  const video = shownId ? VIDEOS[shownId] : undefined;
  const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;

  return (
    <Modal
      open={id !== null && !!VIDEOS[id]}
      onCancel={onClose}
      afterClose={() => setShownId(null)}
      footer={null}
      title={video?.title}
      width="min(1400px, 94vw)"
      destroyOnHidden
    >
      {video && (
        <video
          key={shownId}
          src={video.src}
          poster={video.poster}
          autoPlay={!reduceMotion}
          loop
          muted
          controls
          playsInline
          style={{ width: '100%', display: 'block', borderRadius: 8 }}
        />
      )}
    </Modal>
  );
}
