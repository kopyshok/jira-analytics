import type { Role } from '../types/api';

export const rolesToMap = (roles: Role[]) =>
  Object.fromEntries(roles.map(r => [r.code, r]));

export const getRoleLabel = (roles: Role[], code: string | null | undefined) =>
  code ? (roles.find(r => r.code === code)?.label ?? code) : '—';

export const getRoleColor = (roles: Role[], code: string | null | undefined, fallback = '#888780') =>
  code ? (roles.find(r => r.code === code)?.color ?? fallback) : fallback;
