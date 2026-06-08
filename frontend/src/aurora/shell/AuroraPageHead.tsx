import { type ReactNode } from 'react';

interface Props {
  title: string;
  subtitle?: string;
  extra?: ReactNode;
}

export function AuroraPageHead({ title, subtitle, extra }: Props) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'flex-end',
        justifyContent: 'space-between',
        gap: 16,
        marginBottom: 20,
      }}
    >
      <div>
        {subtitle && <div className="eyebrow" style={{ marginBottom: 5 }}>{subtitle}</div>}
        <div
          className="serif"
          style={{ fontSize: 30, fontWeight: 600, letterSpacing: '-0.02em' }}
        >
          {title}
        </div>
      </div>
      {extra}
    </div>
  );
}
