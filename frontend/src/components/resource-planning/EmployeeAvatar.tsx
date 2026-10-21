import { Tooltip } from 'antd';
import { useSkin } from '../../contexts/ThemeContext';
import { readablePair } from '../../utils/readableColor';

interface Props {
  name: string | null;
  role?: string | null;
  size?: number;
}

const ROLE_COLORS: Record<string, string> = {
  analyst: '#00c9c8',
  аналитик: '#00c9c8',
  rp: '#5470ff',
  рп: '#5470ff',
  consultant: '#a070ff',
  консультант: '#a070ff',
  developer: '#3a7bff',
  разработчик: '#3a7bff',
  программист: '#3a7bff',
  qa: '#f59e0b',
  тестировщик: '#f59e0b',
};

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

export default function EmployeeAvatar({ name, role, size = 22 }: Props) {
  const skin = useSkin();
  if (!name) return null;
  const color = ROLE_COLORS[(role ?? '').toLowerCase()] ?? '#6b7280';
  // В обложке — светлая подложка и тёмные инициалы того же оттенка (контраст ≥ 4.5:1).
  const pair = skin ? readablePair(color) : null;
  return (
    <Tooltip title={name}>
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: size,
          height: size,
          borderRadius: '50%',
          background: pair ? pair.bg : color,
          color: pair ? pair.fg : '#fff',
          boxShadow: pair ? `inset 0 0 0 1px ${pair.border}` : undefined,
          fontSize: Math.round(size * 0.45),
          fontWeight: 600,
          letterSpacing: 0.3,
          flexShrink: 0,
          cursor: 'pointer',
        }}
      >
        {initials(name)}
      </span>
    </Tooltip>
  );
}
