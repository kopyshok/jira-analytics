import { type ReactNode } from 'react';

type Tone = 'good' | 'warn' | 'bad' | 'accent' | 'key';

interface Props {
  children: ReactNode;
  tone?: Tone;
  icon?: ReactNode;
}

export function Badge({ children, tone = 'accent', icon }: Props) {
  return (
    <span className={`badge badge-${tone}`}>
      {icon}{children}
    </span>
  );
}
