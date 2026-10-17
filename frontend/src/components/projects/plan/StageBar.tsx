import React from 'react';
import { stageBar } from '../../../utils/projectsView';

/**
 * Тонкая полоса «факт / план» вида скина: заливка цветом стадии до плана и
 * перерасход отдельным отрезком. Цвета — в CSS раскладки (классы pjc-bar-*).
 */
export const StageBar: React.FC<{ fact: number; plan: number; code: string }> = ({ fact, plan, code }) => {
  const { base, over } = stageBar(fact, plan);
  return (
    <span className="pjc-bar" aria-hidden>
      <span className={`pjc-bar-base is-${code}`} style={{ width: `${base}%` }} />
      {over > 0 && <span className="pjc-bar-over" style={{ width: `${over}%` }} />}
    </span>
  );
};
