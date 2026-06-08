import { type ReactNode } from 'react';

interface Option {
  value: string;
  label: ReactNode;
}

interface Props {
  options: Option[];
  value: string;
  onChange: (v: string) => void;
}

export function Segmented({ options, value, onChange }: Props) {
  return (
    <div className="seg">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          className={value === o.value ? 'active' : ''}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
