import { type ReactNode } from 'react';

interface Tab {
  key: string;
  label: ReactNode;
  icon?: ReactNode;
}

interface Props {
  tabs: Tab[];
  active: string;
  onChange: (key: string) => void;
}

export function GlassTabs({ tabs, active, onChange }: Props) {
  return (
    <div className="gtabs">
      {tabs.map((t) => (
        <button
          key={t.key}
          type="button"
          className={`gtab ${active === t.key ? 'active' : ''}`.trim()}
          onClick={() => onChange(t.key)}
        >
          {t.icon}{t.label}
        </button>
      ))}
    </div>
  );
}
