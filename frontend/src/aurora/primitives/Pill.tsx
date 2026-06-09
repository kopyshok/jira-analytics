import { type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  icon?: ReactNode;
  onClick?: () => void;
}

export function Pill({ children, icon, onClick }: Props) {
  return (
    <span
      className="pill"
      style={{ cursor: onClick ? 'pointer' : undefined }}
      onClick={onClick}
    >
      {icon}{children}
    </span>
  );
}
