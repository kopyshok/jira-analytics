import { type ReactNode, type CSSProperties, type MouseEvent } from 'react';

type Variant = 'primary' | 'ghost';

interface Props {
  children?: ReactNode;
  variant?: Variant;
  onClick?: (e: MouseEvent<HTMLButtonElement>) => void;
  disabled?: boolean;
  loading?: boolean;
  icon?: ReactNode;
  block?: boolean;
  htmlType?: 'button' | 'submit' | 'reset';
  style?: CSSProperties;
  className?: string;
  title?: string;
}

export function GlassButton({
  children,
  variant = 'primary',
  onClick,
  disabled,
  loading,
  icon,
  block,
  htmlType = 'button',
  style,
  className = '',
  title,
}: Props) {
  const variantClass = variant === 'primary' ? 'gbtn-primary' : 'gbtn-ghost';
  return (
    <button
      type={htmlType}
      className={`gbtn ${variantClass} ${className}`.trim()}
      onClick={onClick}
      disabled={disabled || loading}
      title={title}
      style={{
        width: block ? '100%' : undefined,
        opacity: disabled ? 0.5 : 1,
        ...style,
      }}
    >
      {loading ? <span className="num">…</span> : icon}
      {children}
    </button>
  );
}
