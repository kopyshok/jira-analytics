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
  return (
    <Tooltip title={inPlanHint(role, checked)}>
      {/* У неактивной кнопки нет событий мыши — подсказку ловит обёртка. */}
      <span style={{ display: 'inline-block', cursor: disabled ? 'not-allowed' : undefined }}>
        <Switch
          size={size}
          checked={checked}
          loading={loading}
          disabled={disabled}
          aria-label={ariaLabel}
          style={disabled ? { pointerEvents: 'none' } : undefined}
          onChange={onChange}
        />
      </span>
    </Tooltip>
  );
}
