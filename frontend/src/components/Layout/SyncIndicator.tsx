import { useSyncStatus } from '../../hooks/useSync';
import { DARK_THEME } from '../../utils/constants';
import { timeAgo } from '../../utils/format';

/**
 * Compact pill in the app header: coloured dot + "last sync N ago" or "error".
 * Green=fresh, muted=stale (>6h), amber=any error.
 */
export default function SyncIndicator() {
  const { data } = useSyncStatus();

  const hasError = data?.some((r) => r.last_error) ?? false;
  const lastSyncIso = data
    ?.map((r) => r.last_sync)
    .filter((x): x is string => !!x)
    .sort()
    .at(-1) ?? null;

  const now = Date.now();
  const ageHours = lastSyncIso ? (now - new Date(lastSyncIso).getTime()) / 3_600_000 : null;
  const stale = ageHours !== null && ageHours > 6;

  const { dot, label, text } = (() => {
    if (hasError) return { dot: DARK_THEME.amber, label: 'Ошибка синхронизации', text: DARK_THEME.amber };
    if (lastSyncIso === null) return { dot: DARK_THEME.textHint, label: 'Нет данных', text: DARK_THEME.textMuted };
    if (stale) return { dot: DARK_THEME.textHint, label: timeAgo(lastSyncIso), text: DARK_THEME.textMuted };
    return { dot: DARK_THEME.cyanPrimary, label: timeAgo(lastSyncIso), text: DARK_THEME.textSecondary };
  })();

  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 8,
        padding: '6px 12px',
        borderRadius: 999,
        border: `1px solid ${DARK_THEME.border}`,
        background: DARK_THEME.darkAccent,
        fontSize: 12,
        color: text,
        whiteSpace: 'nowrap',
      }}
      title={lastSyncIso ?? 'Никогда'}
    >
      <span
        style={{
          width: 8,
          height: 8,
          borderRadius: '50%',
          background: dot,
          boxShadow: hasError || !stale ? `0 0 8px ${dot}` : 'none',
        }}
      />
      <span style={{ fontWeight: 500 }}>Синхронизация</span>
      <span style={{ color: DARK_THEME.textMuted }}>·</span>
      <span>{label}</span>
    </div>
  );
}
