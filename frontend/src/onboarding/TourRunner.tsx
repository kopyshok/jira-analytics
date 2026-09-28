import { useEffect, useRef, useState } from 'react';
import { Tour } from 'antd';
import { useLocation, useNavigate } from 'react-router';
import { TOURS } from './tours';
import { findTourTarget, prepareStep } from './tourTarget';
import { useOnboarding } from './OnboardingContext';

// Шаг 0 стартует сразу после навигации на страницу экскурсии — там ещё может идти
// первая загрузка данных, поэтому ждём дольше. Остальные шаги переключаются на уже
// отрисованной странице — цель либо есть, либо действительно отсутствует (например,
// сценария или плана ещё нет у новой команды), долгое ожидание там только тормозит.
const FIRST_STEP_TIMEOUT_MS = 8000;
const STEP_TIMEOUT_MS = 1000;

export default function TourRunner() {
  const { activeTourId, endTour, openPanel } = useOnboarding();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState(0);
  const [preparing, setPreparing] = useState(false);
  // Номер запуска: экскурсию закрыли, пока ждали цель, — не открывать её.
  const runRef = useRef(0);
  // Экскурсию обогнали более новым переключением шага (быстро «Далее», потом «Назад») —
  // применяем только результат самого свежего переключения.
  const changeSeqRef = useRef(0);
  // rc-tour на «Готово» вызывает onClose раньше onFinish (см. onClose ниже).
  const finishedRef = useRef(false);
  const tour = activeTourId ? TOURS[activeTourId] : undefined;

  useEffect(() => {
    if (!tour) {
      setOpen(false);
      return;
    }
    const run = ++runRef.current;
    finishedRef.current = false;
    if (tour.route) {
      const [routePath, routeQuery] = tour.route.split('?');
      if (location.pathname !== routePath) {
        navigate(tour.route);
      } else if (routeQuery) {
        // Тот же путь — не терять параметры, которые уже есть в адресе (например,
        // диапазон дат): переносим их и добавляем только то, что требует экскурсия.
        const required = new URLSearchParams(routeQuery);
        const merged = new URLSearchParams(location.search);
        let changed = false;
        required.forEach((value, key) => {
          if (merged.get(key) !== value) {
            merged.set(key, value);
            changed = true;
          }
        });
        if (changed) navigate({ pathname: routePath, search: merged.toString() }, { replace: true });
      }
    }
    void prepareStep(tour.steps[0], FIRST_STEP_TIMEOUT_MS, () => runRef.current === run).then(() => {
      if (runRef.current !== run) return;
      setCurrent(0);
      setOpen(true);
    });
    // Адрес сравнивается только в момент старта экскурсии.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tour, navigate]);

  if (!tour) return null;

  const handleChange = (next: number) => {
    const run = runRef.current;
    const seq = ++changeSeqRef.current;
    const isCurrent = () => runRef.current === run && changeSeqRef.current === seq;
    setPreparing(true);
    void prepareStep(tour.steps[next], STEP_TIMEOUT_MS, isCurrent).then(() => {
      if (isCurrent()) setCurrent(next);
      if (changeSeqRef.current === seq) setPreparing(false);
    });
  };

  const last = tour.steps.length - 1;
  return (
    <Tour
      open={open}
      current={current}
      onChange={handleChange}
      onClose={() => {
        runRef.current++;
        // rc-tour вызывает onClose перед onFinish на «Готово» — откладываем через
        // микротаск и не завершаем как отменённую, если onFinish уже отметился.
        Promise.resolve().then(() => {
          if (finishedRef.current) return;
          endTour(false);
        });
      }}
      onFinish={() => {
        finishedRef.current = true;
        runRef.current++;
        endTour(true);
        // Экскурсию запускали из чек-листа «Первые шаги» — после «Готово»
        // возвращаем пользователя туда продолжать по списку.
        openPanel();
      }}
      steps={tour.steps.map((s, i) => ({
        title: s.title,
        description: s.description,
        // rc-tour типизирует target как «функция без null» либо `() => null` —
        // findTourTarget честно возвращает HTMLElement | null, приводим тип.
        target: (s.target ? () => findTourTarget(s.target as string) : null) as (() => HTMLElement) | null,
        nextButtonProps: {
          // AntD 6 Tour не поддерживает loading у кнопки — показываем ожидание текстом.
          children: i === last ? 'Готово' : (preparing && i === current ? 'Далее…' : 'Далее'),
        },
        prevButtonProps: { children: 'Назад' },
      }))}
    />
  );
}
