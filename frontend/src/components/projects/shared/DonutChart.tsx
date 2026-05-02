import React from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';

interface Slice {
  code: string;
  label: string;
  hours: number;
  color: string;
}

interface Props {
  slices: Slice[];
  centerValue?: string;
  centerLabel?: string;
  size?: number;
  onSliceClick?: (slice: Slice) => void;
}

export const DonutChart: React.FC<Props> = ({
  slices,
  centerValue,
  centerLabel,
  size = 180,
  onSliceClick,
}) => (
  <div style={{ width: size, height: size, position: 'relative' }}>
    <ResponsiveContainer>
      <PieChart>
        <Pie
          data={slices}
          dataKey="hours"
          innerRadius={size * 0.35}
          outerRadius={size * 0.48}
          paddingAngle={1}
          stroke="none"
        >
          {slices.map((s, i) => (
            <Cell
              key={i}
              fill={s.color}
              onClick={onSliceClick ? () => onSliceClick(s) : undefined}
              style={onSliceClick ? { cursor: 'pointer' } : undefined}
            />
          ))}
        </Pie>
      </PieChart>
    </ResponsiveContainer>
    {centerValue && (
      <div
        style={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          pointerEvents: 'none',
        }}
      >
        <div style={{ fontSize: size * 0.18, fontWeight: 700, color: '#fff' }}>{centerValue}</div>
        {centerLabel && <div style={{ fontSize: 11, color: '#7e94b8' }}>{centerLabel}</div>}
      </div>
    )}
  </div>
);
