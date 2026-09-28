import { createContext, useContext } from 'react';
import type { OnboardingMe, OnboardingStatus, StepState } from '../api/onboarding';

export interface OnboardingCtx {
  /** Команда, для которой показан блок настройки; null — в шапке команда не выбрана. */
  team: string | null;
  teamOptions: string[];
  setTeam: (team: string) => void;
  status: OnboardingStatus | undefined;
  panelOpen: boolean;
  openPanel: () => void;
  closePanel: () => void;
  activeTourId: string | null;
  startTour: (id: string) => void;
  endTour: (completed: boolean) => void;
  setStepState: (step: string, state: StepState) => Promise<void>;
  updateMe: (patch: Partial<OnboardingMe>) => Promise<void>;
}

export const Ctx = createContext<OnboardingCtx | null>(null);

export function useOnboarding(): OnboardingCtx {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error('OnboardingProvider is not mounted');
  return ctx;
}
