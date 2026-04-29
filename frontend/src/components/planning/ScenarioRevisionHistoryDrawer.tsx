import { Drawer, Empty, Select, Spin, Table, Tag } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { useScenarioRevisions, useRevisionDiff } from '../../hooks/usePlanning';
import { DARK_THEME, FONTS } from '../../utils/constants';
import type { RevisionDiffEmployee, RevisionDiffMonth } from '../../types/api';

interface Props {
  open: boolean;
  onClose: () => void;
  scenarioId: string | null;
}

const MONTH_NAMES = ['', 'Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн',
                     'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек'];

function formatDate(iso: string): string {
  return new Date(iso).toLocaleString('ru-RU', {
    day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

export default function ScenarioRevisionHistoryDrawer({ open, onClose, scenarioId }: Props) {
  const { data: revisions = [], isLoading } = useScenarioRevisions(scenarioId ?? undefined, open);
  const [r1, setR1] = useState<number | null>(null);
  const [r2, setR2] = useState<number | null>(null);

  useEffect(() => {
    if (!open || revisions.length < 2) return;
    setR1((prev) => prev ?? revisions[revisions.length - 2].revision_number);
    setR2((prev) => prev ?? revisions[revisions.length - 1].revision_number);
  }, [open, revisions]);

  const { data: diff, isLoading: diffLoading } = useRevisionDiff(
    scenarioId ?? undefined, r1, r2,
  );

  const options = useMemo(
    () => revisions.map((r) => ({
      label: `R${r.revision_number} — ${formatDate(r.approved_at)}${r.note ? ` · ${r.note}` : ''}`,
      value: r.revision_number,
    })),
    [revisions],
  );

  return (
    <Drawer
      title="История ревизий сценария"
      open={open}
      onClose={onClose}
      width="80vw"
    >
      {isLoading ? (
        <Spin />
      ) : revisions.length === 0 ? (
        <Empty description="Сценарий ни разу не утверждался" />
      ) : revisions.length < 2 ? (
        <Empty description="Утверждена только одна ревизия — сравнивать не с чем" />
      ) : (
        <>
          <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 11, color: DARK_THEME.textMuted, marginBottom: 4 }}>Базовая ревизия</div>
              <Select
                style={{ width: '100%' }}
                value={r1 ?? undefined}
                onChange={setR1}
                options={options}
              />
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 11, color: DARK_THEME.textMuted, marginBottom: 4 }}>Сравниваемая ревизия</div>
              <Select
                style={{ width: '100%' }}
                value={r2 ?? undefined}
                onChange={setR2}
                options={options}
              />
            </div>
          </div>

          {r1 === r2 ? (
            <Empty description="Выберите две разные ревизии" />
          ) : diffLoading || !diff ? (
            <Spin />
          ) : (
            <DiffBody diff={diff} />
          )}
        </>
      )}
    </Drawer>
  );
}

function DiffBody({ diff }: { diff: NonNullable<ReturnType<typeof useRevisionDiff>['data']> }) {
  const compositionEmpty = diff.added.length === 0 && diff.removed.length === 0;
  const capacityEmpty = diff.capacity.length === 0;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <Header diff={diff} />

      <Section title="Состав инициатив">
        {compositionEmpty ? (
          <div style={{ color: DARK_THEME.textMuted, fontSize: 12 }}>
            Состав не изменился ({diff.kept.length} инициатив).
          </div>
        ) : (
          <div style={{ display: 'flex', gap: 16 }}>
            <ItemColumn
              title={`Добавлено (${diff.added.length})`}
              color="#1d9e75"
              items={diff.added.map((i) => i.backlog_item_name)}
            />
            <ItemColumn
              title={`Убрано (${diff.removed.length})`}
              color="#f5222d"
              items={diff.removed.map((i) => i.backlog_item_name)}
            />
          </div>
        )}
      </Section>

      <Section title="Доступность команды">
        {capacityEmpty ? (
          <div style={{ color: DARK_THEME.textMuted, fontSize: 12 }}>
            Норма и доступность не менялись.
          </div>
        ) : (
          <CapacityTable rows={diff.capacity} />
        )}
      </Section>
    </div>
  );
}

function Header({ diff }: { diff: NonNullable<ReturnType<typeof useRevisionDiff>['data']> }) {
  return (
    <div style={{ display: 'flex', gap: 16, padding: 12, background: 'rgba(0,201,200,0.05)', borderRadius: 6 }}>
      <RevisionCard label="R1" side={diff.r1} />
      <div style={{ display: 'flex', alignItems: 'center', color: DARK_THEME.textMuted, fontSize: 18 }}>→</div>
      <RevisionCard label="R2" side={diff.r2} />
    </div>
  );
}

function RevisionCard({ label, side }: { label: string; side: { revision_number: number; approved_at: string; note: string | null; included_count: number } }) {
  return (
    <div style={{ flex: 1 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Tag color="cyan">{label} · R{side.revision_number}</Tag>
        <span style={{ fontSize: 11, color: DARK_THEME.textMuted }}>{formatDate(side.approved_at)}</span>
      </div>
      <div style={{ fontSize: 12, color: DARK_THEME.textPrimary, marginTop: 4 }}>
        {side.included_count} включённых инициатив
      </div>
      {side.note && (
        <div style={{ fontSize: 11, color: DARK_THEME.textMuted, marginTop: 2, fontStyle: 'italic' }}>
          {side.note}
        </div>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontSize: 13, fontWeight: 600, color: DARK_THEME.textPrimary, marginBottom: 8 }}>{title}</div>
      {children}
    </div>
  );
}

function ItemColumn({ title, color, items }: { title: string; color: string; items: string[] }) {
  return (
    <div style={{ flex: 1 }}>
      <div style={{ fontSize: 12, color, fontWeight: 600, marginBottom: 6 }}>{title}</div>
      {items.length === 0 ? (
        <div style={{ fontSize: 12, color: DARK_THEME.textMuted }}>—</div>
      ) : (
        items.map((name) => (
          <div
            key={name}
            style={{
              padding: '6px 10px', marginBottom: 4,
              background: color === '#1d9e75' ? 'rgba(29,158,117,0.10)' : 'rgba(245,34,45,0.10)',
              borderLeft: `3px solid ${color}`,
              borderRadius: 4,
              fontSize: 12,
              color: DARK_THEME.textPrimary,
            }}
          >
            {name}
          </div>
        ))
      )}
    </div>
  );
}

function CapacityTable({ rows }: { rows: RevisionDiffEmployee[] }) {
  type FlatRow = {
    key: string;
    employee_name: string;
    period: string;
    r1_norm: number;
    r1_available: number;
    r2_norm: number;
    r2_available: number;
    delta_norm: number;
    delta_available: number;
    isTotal: boolean;
  };

  const flat: FlatRow[] = [];
  for (const emp of rows) {
    emp.months.forEach((m: RevisionDiffMonth, idx) => {
      flat.push({
        key: `${emp.employee_id}-${m.year}-${m.month}`,
        employee_name: idx === 0 ? emp.employee_name : '',
        period: `${MONTH_NAMES[m.month]} ${m.year}`,
        r1_norm: m.r1_norm_hours,
        r1_available: m.r1_available_hours,
        r2_norm: m.r2_norm_hours,
        r2_available: m.r2_available_hours,
        delta_norm: m.delta_norm_hours,
        delta_available: m.delta_available_hours,
        isTotal: false,
      });
    });
    flat.push({
      key: `${emp.employee_id}-total`,
      employee_name: '',
      period: 'Σ итого',
      r1_norm: 0, r1_available: 0, r2_norm: 0, r2_available: 0,
      delta_norm: emp.delta_total_norm_hours,
      delta_available: emp.delta_total_available_hours,
      isTotal: true,
    });
  }

  const renderHours = (h: number, isTotal: boolean) =>
    isTotal ? '' : <span style={{ fontFamily: FONTS.mono, fontSize: 12 }}>{Math.round(h)}</span>;
  const renderDelta = (d: number) => (
    <span style={{
      fontFamily: FONTS.mono,
      fontSize: 12,
      fontWeight: 600,
      color: d > 0 ? '#22c55e' : d < 0 ? '#f87171' : DARK_THEME.textMuted,
    }}>
      {d === 0 ? '—' : `${d > 0 ? '+' : ''}${Math.round(d)}`}
    </span>
  );

  return (
    <Table<FlatRow>
      dataSource={flat}
      pagination={false}
      size="small"
      rowClassName={(row) => (row.isTotal ? 'revision-diff-total-row' : '')}
      columns={[
        { title: 'Сотрудник', dataIndex: 'employee_name', width: 200 },
        { title: 'Период', dataIndex: 'period', width: 110 },
        { title: 'R1 норма', dataIndex: 'r1_norm', align: 'right', render: (v, row) => renderHours(v, row.isTotal) },
        { title: 'R1 доступ.', dataIndex: 'r1_available', align: 'right', render: (v, row) => renderHours(v, row.isTotal) },
        { title: 'R2 норма', dataIndex: 'r2_norm', align: 'right', render: (v, row) => renderHours(v, row.isTotal) },
        { title: 'R2 доступ.', dataIndex: 'r2_available', align: 'right', render: (v, row) => renderHours(v, row.isTotal) },
        { title: 'Δ норма', dataIndex: 'delta_norm', align: 'right', render: renderDelta },
        { title: 'Δ доступ.', dataIndex: 'delta_available', align: 'right', render: renderDelta },
      ]}
    />
  );
}
