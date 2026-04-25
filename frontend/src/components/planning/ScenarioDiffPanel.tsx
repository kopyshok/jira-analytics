import { Drawer, Empty, Spin, Tag } from 'antd';
import { useMemo } from 'react';
import { useScenarios, useScenarioAllocations } from '../../hooks/usePlanning';
import { diffScenarios } from '../../utils/scenarioDiff';
import { DARK_THEME, FONTS } from '../../utils/constants';
import type { AllocationResponse, ScenarioResponse } from '../../types/api';

interface Props {
  open: boolean;
  onClose: () => void;
  draftScenario: ScenarioResponse;
  draftAllocations: AllocationResponse[];
}

const SECTION: React.CSSProperties = {
  marginTop: 18,
};
const SECTION_TITLE: React.CSSProperties = {
  fontSize: 12,
  fontWeight: 700,
  color: DARK_THEME.textMuted,
  textTransform: 'uppercase',
  letterSpacing: 0.5,
  marginBottom: 8,
};

export default function ScenarioDiffPanel({
  open, onClose, draftScenario, draftAllocations,
}: Props) {
  // Take the most-recently-created approved scenario for same year+quarter.
  // Backend ждёт quarter как целое 1..4, а в `ScenarioResponse.quarter` лежит строка "Q1".."Q4".
  const quarterInt = draftScenario.quarter
    ? draftScenario.quarter.replace(/^Q/, '')
    : undefined;
  const { data: approvedList } = useScenarios(
    draftScenario.year != null ? String(draftScenario.year) : undefined,
    quarterInt,
    'approved',
  );
  const lastApproved = useMemo(() => {
    if (!approvedList || approvedList.length === 0) return null;
    return approvedList[0];
  }, [approvedList]);
  const { data: approvedAllocs, isLoading } = useScenarioAllocations(
    lastApproved?.id ?? null,
  );

  const diff = useMemo(() => {
    if (!approvedAllocs) return null;
    // A = draft, B = approved
    return diffScenarios(draftAllocations, approvedAllocs);
  }, [draftAllocations, approvedAllocs]);

  return (
    <Drawer
      title={`Diff: «${draftScenario.name}» vs последний утверждённый`}
      open={open}
      onClose={onClose}
      width={620}
    >
      {!lastApproved ? (
        <Empty description="Утверждённых сценариев на этот квартал ещё нет" />
      ) : isLoading || !diff ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
          <Spin />
        </div>
      ) : (
        <>
          <div style={{ fontSize: 12, color: DARK_THEME.textMuted }}>
            Сравниваем с: <strong style={{ color: DARK_THEME.textPrimary }}>{lastApproved.name}</strong>
          </div>

          <div style={SECTION}>
            <div style={SECTION_TITLE}>
              <Tag color="green">Добавлено в черновик</Tag> {diff.onlyInA.length}
            </div>
            {diff.onlyInA.length === 0 ? (
              <div style={{ fontSize: 12, color: DARK_THEME.textHint }}>—</div>
            ) : (
              diff.onlyInA.map((a) => <DiffRow key={a.id} alloc={a} />)
            )}
          </div>

          <div style={SECTION}>
            <div style={SECTION_TITLE}>
              <Tag color="red">Удалено в черновике</Tag> {diff.onlyInB.length}
            </div>
            {diff.onlyInB.length === 0 ? (
              <div style={{ fontSize: 12, color: DARK_THEME.textHint }}>—</div>
            ) : (
              diff.onlyInB.map((a) => <DiffRow key={a.id} alloc={a} />)
            )}
          </div>

          <div style={SECTION}>
            <div style={SECTION_TITLE}>
              <Tag>Без изменений</Tag> {diff.common.length}
            </div>
            {diff.common.length === 0 ? (
              <div style={{ fontSize: 12, color: DARK_THEME.textHint }}>—</div>
            ) : (
              diff.common.map(({ left }) => <DiffRow key={left.id} alloc={left} muted />)
            )}
          </div>
        </>
      )}
    </Drawer>
  );
}

function DiffRow({ alloc, muted }: { alloc: AllocationResponse; muted?: boolean }) {
  return (
    <div
      style={{
        padding: '8px 10px',
        marginBottom: 4,
        background: muted ? 'transparent' : 'rgba(255,255,255,0.03)',
        borderRadius: 4,
        opacity: muted ? 0.65 : 1,
        fontSize: 13,
      }}
    >
      <div style={{ color: DARK_THEME.textPrimary }}>
        {alloc.title}
      </div>
      <div style={{ display: 'flex', gap: 10, fontSize: 11, color: DARK_THEME.textMuted, marginTop: 2 }}>
        {alloc.jira_key && <span style={{ fontFamily: FONTS.mono }}>{alloc.jira_key}</span>}
        {alloc.estimate_hours != null && <span>{Math.round(alloc.estimate_hours)} ч</span>}
        {alloc.assignee_display_name && <span>· {alloc.assignee_display_name}</span>}
      </div>
    </div>
  );
}
