import { Drawer, Empty, Select, Spin, Tag } from 'antd';
import { useMemo, useState } from 'react';
import { useScenarios, useScenarioAllocations } from '../../hooks/usePlanning';
import { diffScenarios } from '../../utils/scenarioDiff';
import { DARK_THEME, FONTS } from '../../utils/constants';
import type { AllocationResponse } from '../../types/api';

interface Props {
  open: boolean;
  onClose: () => void;
  initialScenarioId?: string;
}

const COL: React.CSSProperties = {
  flex: 1,
  minWidth: 0,
  padding: 8,
};

export default function ScenarioCompareDrawer({ open, onClose, initialScenarioId }: Props) {
  const { data: scenarios = [] } = useScenarios();
  const [aId, setAId] = useState<string | undefined>(initialScenarioId);
  const [bId, setBId] = useState<string | undefined>();
  const { data: allocsA, isLoading: la } = useScenarioAllocations(aId ?? null);
  const { data: allocsB, isLoading: lb } = useScenarioAllocations(bId ?? null);

  const diff = useMemo(() => {
    if (!allocsA || !allocsB) return null;
    return diffScenarios(allocsA, allocsB);
  }, [allocsA, allocsB]);

  const sceneOptions = scenarios.map((s) => ({
    label: `${s.name} · ${s.quarter} ${s.year}${s.status === 'approved' ? ' ✓' : ''}`,
    value: s.id,
  }));

  const ready = !!aId && !!bId && !la && !lb && !!diff;

  return (
    <Drawer
      title="Сравнение сценариев"
      open={open}
      onClose={onClose}
      width="80vw"
    >
      <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 11, color: DARK_THEME.textMuted, marginBottom: 4 }}>Сценарий A</div>
          <Select
            style={{ width: '100%' }}
            placeholder="Выберите сценарий"
            value={aId}
            onChange={setAId}
            options={sceneOptions}
            showSearch
            filterOption={(input, opt) =>
              String(opt?.label ?? '').toLowerCase().includes(input.toLowerCase())
            }
          />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 11, color: DARK_THEME.textMuted, marginBottom: 4 }}>Сценарий B</div>
          <Select
            style={{ width: '100%' }}
            placeholder="Выберите сценарий"
            value={bId}
            onChange={setBId}
            options={sceneOptions}
            showSearch
            filterOption={(input, opt) =>
              String(opt?.label ?? '').toLowerCase().includes(input.toLowerCase())
            }
          />
        </div>
      </div>

      {!aId || !bId ? (
        <Empty description="Выберите оба сценария для сравнения" />
      ) : !ready ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
          <Spin />
        </div>
      ) : (
        <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>
          <div style={COL}>
            <ColumnHeader title="A" count={(allocsA ?? []).filter((x) => x.included).length} />
            {[...diff!.common.map((c) => ({ alloc: c.left, state: 'common' as const })),
              ...diff!.onlyInA.map((alloc) => ({ alloc, state: 'onlyA' as const }))]
              .map((row) => (
                <CompareRow key={row.alloc.id} alloc={row.alloc} state={row.state} />
              ))}
          </div>
          <div style={COL}>
            <ColumnHeader title="B" count={(allocsB ?? []).filter((x) => x.included).length} />
            {[...diff!.common.map((c) => ({ alloc: c.right, state: 'common' as const })),
              ...diff!.onlyInB.map((alloc) => ({ alloc, state: 'onlyB' as const }))]
              .map((row) => (
                <CompareRow key={row.alloc.id} alloc={row.alloc} state={row.state} />
              ))}
          </div>
        </div>
      )}
    </Drawer>
  );
}

function ColumnHeader({ title, count }: { title: string; count: number }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, paddingBottom: 8, borderBottom: `1px solid ${DARK_THEME.border}` }}>
      <Tag color="cyan">{title}</Tag>
      <span style={{ fontSize: 12, color: DARK_THEME.textMuted }}>{count} включено</span>
    </div>
  );
}

function CompareRow({ alloc, state }: { alloc: AllocationResponse; state: 'common' | 'onlyA' | 'onlyB' }) {
  const bg =
    state === 'onlyA' ? 'rgba(29,158,117,0.10)' :
    state === 'onlyB' ? 'rgba(245,34,45,0.10)' :
    'transparent';
  const border =
    state === 'onlyA' ? '#1d9e75' :
    state === 'onlyB' ? '#f5222d' :
    'transparent';
  return (
    <div
      style={{
        padding: '8px 10px',
        marginBottom: 4,
        background: bg,
        borderLeft: `3px solid ${border}`,
        borderRadius: 4,
        fontSize: 13,
      }}
    >
      <div style={{ color: DARK_THEME.textPrimary }}>{alloc.title}</div>
      <div style={{ display: 'flex', gap: 10, fontSize: 11, color: DARK_THEME.textMuted, marginTop: 2 }}>
        {alloc.jira_key && <span style={{ fontFamily: FONTS.mono }}>{alloc.jira_key}</span>}
        {alloc.estimate_hours != null && <span>{Math.round(alloc.estimate_hours)} ч</span>}
        {alloc.assignee_display_name && <span>· {alloc.assignee_display_name}</span>}
      </div>
    </div>
  );
}
