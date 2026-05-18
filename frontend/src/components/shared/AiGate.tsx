import React from 'react';
import { Tooltip } from 'antd';
import { useAiEnabled } from '../../hooks/useAiEnabled';

const DISABLED_MSG = 'ИИ выключен администратором';

type Props = {
  /** Один React-element (Button/IconButton). Будет disabled при выкл. ИИ. */
  children: React.ReactElement;
  /** Кастомный текст тултипа. */
  message?: string;
};

/**
 * Оборачивает интерактивный элемент (кнопку и т.п.): если ИИ выключен,
 * прокидывает `disabled` в child и показывает Tooltip с подсказкой.
 *
 * При включённом ИИ — рендерит ребёнка as-is.
 */
export const AiGate: React.FC<Props> = ({ children, message = DISABLED_MSG }) => {
  const { enabled } = useAiEnabled();
  if (enabled) return children;

  const child = React.cloneElement(children as React.ReactElement<{ disabled?: boolean }>, {
    disabled: true,
  });
  return (
    <Tooltip title={message}>
      {/* Tooltip не показывается на disabled-кнопках без обёртки. */}
      <span style={{ display: 'inline-block', cursor: 'not-allowed' }}>{child}</span>
    </Tooltip>
  );
};
