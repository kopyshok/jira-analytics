interface Props {
  name: string;
  color?: string;
  size?: number;
}

export function Avatar({ name, color = 'var(--accent-1)', size = 28 }: Props) {
  const ini = name
    .split(' ')
    .map((w) => w[0] || '')
    .join('')
    .toUpperCase()
    .slice(0, 2);
  return (
    <span
      style={{
        width: size,
        height: size,
        borderRadius: '50%',
        flexShrink: 0,
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: size * 0.4,
        fontWeight: 700,
        color: 'var(--on-accent)',
        background: `linear-gradient(135deg, ${color}, var(--accent-2))`,
        boxShadow: '0 0 0 1px var(--glass-border)',
      }}
    >
      {ini}
    </span>
  );
}
