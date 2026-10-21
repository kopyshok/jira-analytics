import { describe, expect, it, vi } from 'vitest';
import { QueryClient } from '@tanstack/react-query';
import { APPEARANCE_QUERY_KEY, patchAppearance, type AppearanceSettings } from './appearance';
import { api } from './client';

vi.mock('./client', () => ({ api: { get: vi.fn(), put: vi.fn() } }));

const saved: AppearanceSettings = {
  phase_colors: { analyst: '#111111', dev: '#222222', qa: '#333333', opo: '#444444' },
  initiative_bracket_color: '#555555',
  initiative_fill_intensity: 'dense',
  animation_speed_seconds: 3,
  hours_balance_lag_days: 0,
  scenario_lift_included: true,
};

describe('patchAppearance', () => {
  it('меняет одну настройку поверх сохранённых на сервере, а не того, что видит экран', async () => {
    const qc = new QueryClient();
    // На экране — значения по умолчанию (виджет вне поставщика настроек).
    qc.setQueryData(APPEARANCE_QUERY_KEY, { ...saved, phase_colors: { analyst: '#0', dev: '#0', qa: '#0', opo: '#0' } });
    vi.mocked(api.get).mockResolvedValue(saved);
    vi.mocked(api.put).mockImplementation(async (_url, body) => body);

    await patchAppearance(qc, { hours_balance_lag_days: 2 });

    expect(api.put).toHaveBeenCalledWith('/users/me/appearance', { ...saved, hours_balance_lag_days: 2 });
  });
});
