import { type ReactNode, type CSSProperties } from 'react';

interface Props {
  children: ReactNode;
  hover?: boolean;
  padding?: number | string;
  style?: CSSProperties;
  className?: string;
  onClick?: () => void;
  title?: ReactNode;
  extra?: ReactNode;
}

export function GlassCard({
  children,
  hover,
  padding = 20,
  style,
  className = '',
  onClick,
  title,
  extra,
}: Props) {
  const paddingValue = typeof padding === 'number' ? `${padding}px` : padding;
  return (
    <div
      className={`glass ${hover ? 'glass-hover' : ''} ${className}`.trim()}
      style={{ padding: paddingValue, ...style }}
      onClick={onClick}
    >
      {(title || extra) && (
        <div className="card-title" style={{ marginBottom: 14 }}>
          <span>{title}</span>
          {extra}
        </div>
      )}
      {children}
    </div>
  );
}
