// @vitest-environment jsdom
import { App } from 'antd';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest';
import ConnectionCard from '../ConnectionCard';
import ConfluenceConnectionCard from '../ConfluenceConnectionCard';
import TokenRenewalNote from './TokenRenewalNote';

const mocks = vi.hoisted(() => ({
  save: vi.fn(),
  pending: false,
  state: { expires_at: null as string | null, expiry_known: true },
}));
vi.mock('../../hooks/useSettings', () => ({
  useJiraSettings: () => ({ data: {
    base_url: 'https://jira.example.test', has_token: true,
    token_expiry_known: true, token_expires_at: null,
  } }),
  useConfluenceSettings: () => ({ data: {
    base_url: 'https://wiki.example.test', has_token: true,
    token_expiry_known: true, token_expires_at: null,
  } }),
  useSaveJiraSettings: () => ({ mutate: mocks.save, isPending: mocks.pending }),
  useSaveConfluenceSettings: () => ({ mutate: mocks.save, isPending: mocks.pending }),
  useTestJiraCredentials: () => ({}),
  useTestConfluenceConnection: () => ({}),
  useTokenRenewal: () => ({ data: { enabled: true, jira: mocks.state, confluence: mocks.state } }),
}));

beforeAll(() => {
  window.matchMedia ??= ((query: string) => ({
    matches: false, media: query, onchange: null,
    addListener: () => {}, removeListener: () => {},
    addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia;
});
afterEach(() => {
  cleanup();
  mocks.save.mockReset();
  mocks.pending = false;
  mocks.state = { expires_at: null, expiry_known: true };
});

describe.each([ConnectionCard, ConfluenceConnectionCard])('срок ключа в подключении', (Card) => {
  it('не допускает потери новых правок, пока сохраняется предыдущий выбор', () => {
    mocks.pending = true;
    render(<App><Card /></App>);
    expect((screen.getByPlaceholderText(/Токен сохранён/) as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByPlaceholderText(/Адрес /) as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText('Без ограничения срока') as HTMLInputElement).disabled).toBe(true);
    expect((screen.getByLabelText('До даты') as HTMLInputElement).disabled).toBe(true);
  });

  it('сохраняет выбранную бессрочность вместе с новым ключом', () => {
    render(<App><Card /></App>);
    fireEvent.change(screen.getByPlaceholderText(/Токен сохранён/), { target: { value: 'manual' } });
    fireEvent.click(screen.getByLabelText('Без ограничения срока'));
    fireEvent.click(screen.getByRole('button', { name: /Сохранить/ }));
    expect(mocks.save.mock.calls[0][0]).toMatchObject({ api_token: 'manual', token_expires_at: null });
  });

  it('не переносит бессрочность старого ключа на новый без выбора срока', () => {
    render(<App><Card /></App>);
    fireEvent.change(screen.getByPlaceholderText(/Токен сохранён/), { target: { value: 'another' } });
    fireEvent.click(screen.getByRole('button', { name: /Сохранить/ }));
    expect(mocks.save.mock.calls[0][0]).not.toHaveProperty('token_expires_at');
  });

  it('сохраняет дату окончания текущего ключа с часовым поясом', () => {
    render(<App><Card /></App>);
    fireEvent.click(screen.getByLabelText('До даты'));
    fireEvent.change(screen.getByLabelText('Дата и время окончания'), { target: { value: '2026-12-01T15:00' } });
    fireEvent.click(screen.getByRole('button', { name: /Сохранить/ }));
    expect(mocks.save.mock.calls[0][0].token_expires_at).toBe(new Date('2026-12-01T15:00').toISOString());
    expect(mocks.save.mock.calls[0][0]).not.toHaveProperty('api_token');
  });

  it('не сохраняет выбранный срок без даты', () => {
    render(<App><Card /></App>);
    fireEvent.click(screen.getByLabelText('До даты'));
    fireEvent.click(screen.getByRole('button', { name: /Сохранить/ }));
    expect(mocks.save).not.toHaveBeenCalled();
  });
});

it('различает бессрочный ключ и неизвестный срок в подписи', () => {
  const view = render(<TokenRenewalNote system="jira" />);
  expect(screen.getByText('Ключ бессрочный, автоматическая замена не требуется')).toBeTruthy();
  mocks.state.expiry_known = false;
  view.rerender(<TokenRenewalNote system="jira" />);
  expect(screen.getByText('Срок ключа не указан. Автоматическая замена приостановлена')).toBeTruthy();
});
