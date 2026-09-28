import { useCallback, useMemo, useState, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { App } from 'antd';
import {
  getOnboardingStatus, putOnboardingMe, putTeamStep,
  type OnboardingMe, type OnboardingStatus, type StepState,
} from '../api/onboarding';
import { useAuth } from '../hooks/useAuth';
import { useGlobalTeamFilter } from '../hooks/useGlobalTeamFilter';
import { useUnreadReleaseNotes } from '../hooks/useReleaseNotes';
import { Ctx, type OnboardingCtx } from './OnboardingContext';

// Кому панель уже открыта автоматически в этой вкладке (module-level, как
// shownInSession в WhatsNewGate.tsx): сервер защёлкивает auto_opened, но до
// ответа PUT ещё один рендер не должен открыть панель снова. Ключ — пользователь:
// после смены учётки в той же вкладке новому пользователю панель откроется.
const autoOpenedFor = new Set<string>();

export function OnboardingProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const { message } = App.useApp();
  const { user } = useAuth();
  const { selectedTeams } = useGlobalTeamFilter();
  const [pickedTeam, setPickedTeam] = useState<string | null>(null);
  const team = pickedTeam && selectedTeams.includes(pickedTeam) ? pickedTeam : (selectedTeams[0] ?? null);

  const { data: status, refetch } = useQuery({
    queryKey: ['onboarding', user?.id, team],
    queryFn: () => getOnboardingStatus(team),
    staleTime: 60_000,
    enabled: !!user,
    refetchOnWindowFocus: false,
  });

  const [panelOpen, setPanelOpen] = useState(false);
  const [activeTourId, setActiveTourId] = useState<string | null>(null);

  const updateMe = useCallback(async (patch: Partial<OnboardingMe>) => {
    // Кэш общий на всё приложение (react-query — синглтон) — без id пользователя
    // данные одного пользователя утекали бы другому после смены учётки в той же вкладке.
    const prefix = ['onboarding', user?.id];
    await qc.cancelQueries({ queryKey: prefix });
    const me = await putOnboardingMe(patch);
    qc.setQueriesData<OnboardingStatus>({ queryKey: prefix }, old => (old ? { ...old, me } : old));
  }, [qc, user?.id]);

  const openPanel = useCallback(() => {
    setPanelOpen(true);
    if (status?.me.hidden) {
      // Сначала снимаем hidden и только потом перечитываем статус — иначе GET,
      // запущенный параллельно с PUT, мог прийти позже и вернуть панель к hidden: true.
      void updateMe({ hidden: false })
        .catch(() => message.error('Не удалось сохранить настройку'))
        .finally(() => void refetch());
    } else {
      void refetch();
    }
  }, [refetch, status?.me.hidden, updateMe, message]);

  const closePanel = useCallback(() => setPanelOpen(false), []);

  const startTour = useCallback((id: string) => {
    setPanelOpen(false);
    setActiveTourId(id);
  }, []);

  const endTour = useCallback((completed: boolean) => {
    const id = activeTourId;
    setActiveTourId(null);
    if (!completed || !id) return;
    // Не берём completed_tours из status (значение на момент рендера) — свежую
    // отметку из другого места могло уже положить в кэш, а этот PUT её стёр бы.
    const cached = qc.getQueryData<OnboardingStatus>(['onboarding', user?.id, team])
      ?? qc.getQueriesData<OnboardingStatus>({ queryKey: ['onboarding', user?.id] })[0]?.[1];
    if (!cached) return;
    const done = cached.me.completed_tours;
    if (!done.includes(id)) {
      void updateMe({ completed_tours: [...done, id] })
        .catch(() => message.error('Не удалось отметить экскурсию пройденной'));
    }
  }, [activeTourId, qc, team, user?.id, updateMe, message]);

  const setStepState = useCallback(async (step: string, state: StepState) => {
    if (!team) return;
    await putTeamStep(step, team, state);
    await qc.invalidateQueries({ queryKey: ['onboarding', user?.id, team] });
  }, [qc, team, user?.id]);

  // Автооткрытие один раз на пользователя, когда пришёл статус и закрыто окно
  // «Что нового» (чтобы два окна не всплыли разом). setState — не внутри
  // useEffect и не синхронно в теле рендера (правила react-hooks/set-state-in-effect,
  // set-state-in-render, react-hooks/globals): откладываем через микротаск и
  // отмечаем себя через мутацию Set, а не переприсвоение переменной — по
  // образцу WhatsNewGate.tsx.
  const { data: unread } = useUnreadReleaseNotes(!!user);
  const whatsNewPending = !unread || unread.unread_versions.length > 0;
  if (status && !status.me.auto_opened && !status.me.hidden && !whatsNewPending && user && !autoOpenedFor.has(user.id)) {
    autoOpenedFor.add(user.id);
    Promise.resolve().then(() => {
      setPanelOpen(true);
      // auto_opened — служебная отметка, молча пробуем ещё раз при следующем входе.
      void updateMe({ auto_opened: true }).catch(() => {});
    });
  }

  const value = useMemo<OnboardingCtx>(() => ({
    team, teamOptions: selectedTeams, setTeam: setPickedTeam, status,
    panelOpen, openPanel, closePanel, activeTourId, startTour, endTour, setStepState, updateMe,
  }), [team, selectedTeams, status, panelOpen, openPanel, closePanel, activeTourId, startTour, endTour, setStepState, updateMe]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
