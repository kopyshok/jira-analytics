import { api } from './client';

export type StepState = 'done' | 'skipped' | 'pending';

export interface StepStatus {
  state: StepState;
  source: 'auto' | 'manual' | null;
  marked_by: string | null;
  marked_at: string | null;
}

export interface OnboardingMe {
  completed_tours: string[];
  auto_opened: boolean;
  hidden: boolean;
}

export interface OnboardingStatus {
  team: string | null;
  steps: Record<string, StepStatus>;
  me: OnboardingMe;
}

export const getOnboardingStatus = (team: string | null) =>
  api.get<OnboardingStatus>('/onboarding/status', { team: team ?? undefined });

export const putTeamStep = (step: string, team: string, state: StepState) =>
  api.put<{ ok: boolean }>(`/onboarding/team-steps/${step}`, { team, state });

export const putOnboardingMe = (data: Partial<OnboardingMe>) =>
  api.put<OnboardingMe>('/onboarding/me', data);
