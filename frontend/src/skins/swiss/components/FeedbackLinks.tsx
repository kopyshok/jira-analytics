import FeedbackDrawer from '../../../components/feedback/FeedbackDrawer';
import { useFeedbackActions } from '../../../components/feedback/useFeedbackActions';

/** «Обратная связь: Открыть форму · Быстрый баг» — строкой внизу паспорта экрана. */
export default function FeedbackLinks() {
  const { open, setOpen, busy, count, handleQuickBug } = useFeedbackActions();
  return (
    <div className="sw-feedback">
      <span>Обратная связь:</span>
      <button type="button" onClick={() => setOpen(true)}>Открыть форму</button>
      <button type="button" onClick={handleQuickBug} disabled={busy}>
        Быстрый баг{count > 0 ? ` · ${count}` : ''}
      </button>
      <FeedbackDrawer open={open} onClose={() => setOpen(false)} />
    </div>
  );
}
