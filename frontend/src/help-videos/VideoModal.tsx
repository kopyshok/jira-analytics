import { Modal } from 'antd';
import { VIDEOS } from './videos';

interface Props {
  id: string | null;
  onClose: () => void;
}

/** Окно с роликом-инструкцией почти на весь экран. Неизвестный id — ничего не показывает. */
export default function VideoModal({ id, onClose }: Props) {
  const video = id ? VIDEOS[id] : undefined;

  return (
    <Modal
      open={!!video}
      onCancel={onClose}
      footer={null}
      title={video?.title}
      width="min(1400px, 94vw)"
      destroyOnHidden
    >
      {video && (
        <video
          key={id}
          src={video.src}
          poster={video.poster}
          autoPlay
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
