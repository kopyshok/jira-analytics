import { Typography } from 'antd';
import { useThemeTokens } from '../../aurora/theme/useThemeTokens';
import type { KpiFunnelStep } from '../../api/kpi';

const { Text } = Typography;

/**
 * Воронка отбора: сколько задач осталось после каждого условия и сколько оно
 * отсекло. Когда метрика показывает «нет данных», это единственное, что
 * отвечает на вопрос «какое условие всё съело» — поэтому шаг, отсёкший больше
 * половины остатка, подсвечивается.
 *
 * Общий компонент для предпросмотра в конструкторе и панели расчёта под
 * ведомостью: обе показывают одно и то же, считанное одним кодом на сервере.
 */
export default function KpiFunnel({ steps, title }: { steps: KpiFunnelStep[]; title?: string }) {
  const t = useThemeTokens();
  if (!steps.length) return null;

  return (
    <div style={{ border: `1px solid ${t.border}`, borderRadius: 10, overflow: 'hidden' }}>
      {title && (
        <div style={{ padding: '8px 12px', borderBottom: `1px solid ${t.border}`, background: t.darkAccent }}>
          <Text style={{ fontSize: 12, fontWeight: 700 }}>{title}</Text>
        </div>
      )}
      <div
        style={{
          display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 70px 70px', gap: 8,
          padding: '6px 12px', borderBottom: `1px solid ${t.border}`,
          fontSize: 10, letterSpacing: '0.08em', textTransform: 'uppercase',
          fontWeight: 700, color: t.textMuted,
        }}
      >
        <span>Условие</span>
        <span style={{ textAlign: 'right' }}>Осталось</span>
        <span style={{ textAlign: 'right' }}>Отсеяно</span>
      </div>
      {steps.map((s, i) => {
        const previous = i > 0 ? steps[i - 1].remaining : null;
        const killer = previous != null && previous > 0 && (s.dropped ?? 0) > previous / 2;
        return (
          <div
            key={`${s.label}-${i}`}
            style={{
              display: 'grid', gridTemplateColumns: 'minmax(0,1fr) 70px 70px', gap: 8,
              padding: '7px 12px', fontSize: 12.5, alignItems: 'center',
              borderBottom: i < steps.length - 1 ? `1px solid ${t.darkRows}` : 'none',
              background: killer ? `color-mix(in srgb, ${t.danger} 10%, transparent)` : undefined,
            }}
          >
            <span style={{ minWidth: 0, overflowWrap: 'anywhere' }}>{s.label}</span>
            <span className="num" style={{ textAlign: 'right', fontWeight: 600 }}>{s.remaining}</span>
            <span
              className="num"
              style={{
                textAlign: 'right',
                color: killer ? t.danger : t.textMuted,
                fontWeight: killer ? 700 : 400,
              }}
            >
              {s.dropped == null ? '—' : `−${s.dropped}`}
            </span>
          </div>
        );
      })}
    </div>
  );
}
