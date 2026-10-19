import dayjs from 'dayjs';
import type { TokenRenewalSystem } from '../../types/api';

/** Причина сбоя продления без точки в конце — чтобы встала в предложение. */
export function renewalReason(error: string): string {
  return error.replace(/[.\s]+$/, '');
}

/** Дата окончания ключа и истёк ли он уже; срок неизвестен — null. */
export function renewalExpiry(state: TokenRenewalSystem): { date: string; expired: boolean } | null {
  if (!state.expires_at) return null;
  const at = dayjs(state.expires_at);
  return { date: at.format('DD.MM.YYYY'), expired: at.isBefore(dayjs()) };
}
