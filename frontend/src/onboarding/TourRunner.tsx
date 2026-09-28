import { useEffect, useRef, useState } from 'react';
import { Tour } from 'antd';
import { useLocation, useNavigate } from 'react-router';
import { TOURS } from './tours';
import { findTourTarget, prepareStep } from './tourTarget';
import { useOnboarding } from './OnboardingContext';

export default function TourRunner() {
  const { activeTourId, endTour } = useOnboarding();
  const navigate = useNavigate();
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [current, setCurrent] = useState(0);
  // Номер запуска: экскурсию закрыли, пока ждали цель, — не открывать её.
  const runRef = useRef(0);
  const tour = activeTourId ? TOURS[activeTourId] : undefined;
  const here = location.pathname + location.search;

  useEffect(() => {
    if (!tour) {
      setOpen(false);
      return;
    }
    const run = ++runRef.current;
    if (tour.route && here !== tour.route) navigate(tour.route);
    void prepareStep(tour.steps[0]).then(() => {
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
    void prepareStep(tour.steps[next]).then(() => {
      if (runRef.current === run) setCurrent(next);
    });
  };

  const last = tour.steps.length - 1;
  return (
    <Tour
      open={open}
      current={current}
      onChange={handleChange}
      onClose={() => { runRef.current++; endTour(false); }}
      onFinish={() => { runRef.current++; endTour(true); }}
      steps={tour.steps.map((s, i) => ({
        title: s.title,
        description: s.description,
        // rc-tour типизирует target как «функция без null» либо `() => null` —
        // findTourTarget честно возвращает HTMLElement | null, приводим тип.
        target: (s.target ? () => findTourTarget(s.target as string) : null) as (() => HTMLElement) | null,
        nextButtonProps: { children: i === last ? 'Готово' : 'Далее' },
        prevButtonProps: { children: 'Назад' },
      }))}
    />
  );
}
