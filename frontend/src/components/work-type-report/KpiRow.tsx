import { Card, Col, Row } from 'antd';
import { DARK_THEME } from '../../utils/constants';
import type { ReportTotals } from '../../types/workTypeReport';

interface Props {
  totals: ReportTotals;
}

interface KpiCardProps {
  value: number;
  label: string;
  format?: (v: number) => string;
}

function KpiCard({ value, label, format }: KpiCardProps) {
  const display = format ? format(value) : String(value);
  return (
    <Card
      size="small"
      style={{
        background: DARK_THEME.cardBg,
        border: `1px solid ${DARK_THEME.border}`,
        textAlign: 'center',
      }}
      styles={{ body: { padding: '16px 12px' } }}
    >
      <div
        style={{
          fontSize: 32,
          fontWeight: 700,
          color: DARK_THEME.textPrimary,
          lineHeight: 1.1,
          marginBottom: 4,
        }}
      >
        {display}
      </div>
      <div style={{ fontSize: 12, color: DARK_THEME.textMuted, marginBottom: 8 }}>{label}</div>
      {/* Sparkline placeholder — will be replaced in Task 13 */}
      <div
        style={{
          height: 40,
          opacity: 0.4,
          background: `linear-gradient(90deg, ${DARK_THEME.border} 0%, transparent 100%)`,
          borderRadius: 4,
        }}
      />
    </Card>
  );
}

export default function KpiRow({ totals }: Props) {
  return (
    <Row gutter={[12, 12]} style={{ marginBottom: 20 }}>
      <Col xs={12} lg={6}>
        <KpiCard value={totals.hours} label="Часов" format={(v) => Math.round(v).toLocaleString('ru')} />
      </Col>
      <Col xs={12} lg={6}>
        <KpiCard value={totals.themes_count} label="Тем" />
      </Col>
      <Col xs={12} lg={6}>
        <KpiCard value={totals.tasks} label="Задач" format={(v) => v.toLocaleString('ru')} />
      </Col>
      <Col xs={12} lg={6}>
        <KpiCard value={totals.employees} label="Сотрудников" />
      </Col>
    </Row>
  );
}
