import type { Role } from '../types/api';
import { readablePair } from '../skins/zones/readableColor';

export const rolesToMap = (roles: Role[]) =>
  Object.fromEntries(roles.map(r => [r.code, r]));

export const getRoleLabel = (roles: Role[], code: string | null | undefined) =>
  code ? (roles.find(r => r.code === code)?.label ?? code) : '—';

export const getRoleColor = (roles: Role[], code: string | null | undefined, fallback = '#888780') =>
  code ? (roles.find(r => r.code === code)?.color ?? fallback) : fallback;

/** Скин поверх Aurora включён (`<html data-skin>`). */
const skinActive = () =>
  typeof document !== 'undefined' && document.documentElement.hasAttribute('data-skin');

/**
 * Цвет роли для ТЕКСТА: в скине — тёмный оттенок того же цвета (контраст ≥ 4.5
 * на светлом), без скина — цвет из справочника как есть.
 */
export const getRoleTextColor = (roles: Role[], code: string | null | undefined, fallback = '#888780') => {
  const color = getRoleColor(roles, code, fallback);
  return skinActive() ? readablePair(color).fg : color;
};

/** Плашка с подписью цветом роли: в скине — светлая подложка и тёмный текст того же оттенка. */
export const roleChipColors = (color: string, darkText: string): { bg: string; fg: string } => {
  if (!skinActive()) return { bg: color, fg: darkText };
  const pair = readablePair(color);
  return { bg: pair.bg, fg: pair.fg };
};
