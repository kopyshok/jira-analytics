import { useId } from 'react';
import { Switch, Tooltip } from 'antd';
import type { SwitchProps } from 'antd';
import { inPlanDisabled, inPlanHint, type InPlanRole } from '../../utils/inPlan';

interface Props {
  role: InPlanRole;
  checked: boolean;
  loading?: boolean;
  size?: SwitchProps['size'];
  ariaLabel: string;
  onChange: (next: boolean) => void;
}

/** Переключатель «В план» с подсказкой, что он значит для этой строки. */
export default function InPlanSwitch({ role, checked, loading, size, ariaLabel, onChange }: Props) {
  const disabled = inPlanDisabled(role, checked);
  const hint = inPlanHint(role, checked);
  const hintId = useId();
  return (
    <Tooltip title={hint}>
      {/* У неактивной кнопки нет событий мыши — подсказку ловит обёртка. */}
      <span style={{ display: 'inline-block', cursor: disabled ? 'not-allowed' : undefined }}>
        <Switch
          size={size}
          checked={checked}
          loading={loading}
          disabled={disabled}
          aria-label={ariaLabel}
          // Всплывающую подсказку не увидеть с клавиатуры, а неактивный
          // переключатель и фокус не получит — смысл и причину читает диктор.
          aria-describedby={hintId}
          style={disabled ? { pointerEvents: 'none' } : undefined}
          onChange={onChange}
        />
        <span id={hintId} hidden>{hint}</span>
      </span>
    </Tooltip>
  );
}
