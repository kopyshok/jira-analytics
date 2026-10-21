import type { Role } from '../types/api';
import { currentSkin } from './constants';
import { readableInk, readablePair, type ReadablePair } from './readableColor';

export const rolesToMap = (roles: Role[]) =>
  Object.fromEntries(roles.map(r => [r.code, r]));

export const getRoleLabel = (roles: Role[], code: string | null | undefined) =>
  code ? (roles.find(r => r.code === code)?.label ?? code) : '—';

export const getRoleColor = (roles: Role[], code: string | null | undefined, fallback = '#888780') =>
  code ? (roles.find(r => r.code === code)?.color ?? fallback) : fallback;

/** Цвет роли для текста: в обложке — затемнённый до читаемого на светлом (≥ 4.5:1). */
export const getRoleInk = (roles: Role[], code: string | null | undefined, fallback = '#888780') => {
  const color = getRoleColor(roles, code, fallback);
  return currentSkin() ? readableInk(color) : color;
};

/** Фишка роли с текстом: в обложке — светлая подложка и тёмный текст того же оттенка; иначе null. */
export const roleChipPair = (color: string): ReadablePair | null =>
  currentSkin() ? readablePair(color) : null;
