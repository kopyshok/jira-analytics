import { type ReactNode } from 'react';

interface PayloadItem {
  name: string;
  value: number;
  color: string;
}

interface Props {
  active?: boolean;
  payload?: PayloadItem[];
  label?: ReactNode;
}

export function GlassTooltip({ active, payload, label }: Props) {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div className="glass" style={{ padding: '10px 14px', minWidth: 140 }}>
      {label !== undefined && (
        <div className="eyebrow" style={{ marginBottom: 6 }}>{label}</div>
      )}
      {payload.map((p) => (
        <div
          key={p.name}
          style={{ display: 'flex', justifyContent: 'space-between', gap: 12, fontSize: 13 }}
        >
          <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span
              style={{
                width: 8,
                height: 8,
                borderRadius: '50%',
                background: p.color,
              }}
            />
            {p.name}
          </span>
          <span className="num" style={{ fontWeight: 600 }}>{p.value}</span>
        </div>
      ))}
    </div>
  );
}
