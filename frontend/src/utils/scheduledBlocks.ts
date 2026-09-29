/** Подпись «Кому» заблокированного периода. */
export function blockAudience(b: { role_labels?: string[]; employee_names?: string[] }): string {
  const roles = (b.role_labels ?? []).join(', ');
  const people = (b.employee_names ?? []).join(', ');
  if (!roles && !people) return 'вся команда';
  return [roles, people].filter(Boolean).join(' · ');
}
