import { useCallback, useState } from 'react';
import { useUnreadReleaseNotes, useMarkSeen } from '../../hooks/useReleaseNotes';
import { useAuth } from '../../hooks/useAuth';
import WhatsNewModal from './WhatsNewModal';

/**
 * Версии, уже показанные в текущей сессии (модульный уровень — сбрасывается только при
 * перезагрузке страницы). Позволяет избежать useState/useRef в теле рендера и useEffect.
 */
const shownInSession = new Set<string>();

/**
 * Глобальный gate, открывающий модалку «Что нового» при первом заходе после релиза.
 * Открывает модалку один раз за сессию при наличии непрочитанных версий.
 * На иконке справки висит красная точка пока пользователь не нажмёт «Понятно».
 */
export default function WhatsNewGate() {
  const { user } = useAuth();
  const { data } = useUnreadReleaseNotes();
  const markSeen = useMarkSeen();

  const topVersion = data?.feeds[0]?.version ?? null;
  const hasUnread = (data?.unread_versions.length ?? 0) > 0;

  // open инициализируется true если это первый рендер с непрочитанной версией
  const [open, setOpen] = useState<boolean>(() => {
    if (!hasUnread || !topVersion) return false;
    if (shownInSession.has(topVersion)) return false;
    shownInSession.add(topVersion);
    return true;
  });

  // Если после инвалидации кэша появилась новая версия — открыть снова
  if (hasUnread && topVersion && !shownInSession.has(topVersion)) {
    shownInSession.add(topVersion);
    Promise.resolve().then(() => setOpen(true));
  }

  const handleClose = useCallback(() => setOpen(false), []);
  const handleMarkSeen = useCallback((v: string) => markSeen.mutate(v), [markSeen]);

  if (!user || !data || data.feeds.length === 0) return null;

  return (
    <WhatsNewModal
      open={open}
      feeds={data.feeds}
      onClose={handleClose}
      onMarkSeen={handleMarkSeen}
    />
  );
}
