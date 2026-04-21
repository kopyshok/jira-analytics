// Маппинг Jira statusCategory.key → цвет AntD Tag. Плюс строковые overrides
// для специальных статусов: "Отменено" / "Cancelled" / "Rejected" попадают
// в категорию 'done' в Jira, но визуально это не done — красим в grey.
export function statusTagColor(
  statusName: string | null | undefined,
  category: string | null | undefined,
): string {
  const lower = (statusName || '').toLowerCase();
  if (lower.includes('отмен') || lower.includes('cancel') || lower.includes('reject')) return 'default';
  switch (category) {
    case 'done': return 'success';
    case 'indeterminate': return 'processing';
    case 'new': return 'default';
    default: return 'default';
  }
}
