import { Checkbox, Card, Button, Radio, Space } from 'antd';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../../api/client';
import HoursBreakdownTable from '../hours/HoursBreakdownTable';
import PlanConflictBanner from '../hours/PlanConflictBanner';
import PlanEditDrawer from '../hours/PlanEditDrawer';
import { useHoursBreakdown } from '../../hooks/useHoursBreakdown';

type RoleVals = { analyst: number | null; dev: number | null; qa: number | null; opo: number | null };

interface ChildItem {
  id: string;
  issue_id: string;
  key: string;
  title: string;
  issue_type: string | null;
  status: string | null;
  included_in_planning: boolean;
}

interface Props {
  backlogItemId: string;
  issueId: string;
  issueKey: string;
  planningMode: 'whole' | 'by_epics';
  includedInPlanning: boolean;
  hasChildren: boolean;
  jiraValues: RoleVals;
  effectiveValues: RoleVals;
  year: number;
  quarter: number;
  children?: ChildItem[];
}

export default function RfaExpandedRow(p: Props) {
  const qc = useQueryClient();
  const { data, isLoading } = useHoursBreakdown(p.issueId, p.year, p.quarter);
  const [editOpen, setEditOpen] = useState(false);

  const modeMut = useMutation({
    mutationFn: (mode: 'whole' | 'by_epics') =>
      api.patch(`/backlog/${p.backlogItemId}/planning-mode`, { mode }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['backlog'] }); },
  });

  const incMut = useMutation({
    mutationFn: ({ id, included }: { id: string; included: boolean }) =>
      api.patch(`/backlog/${id}/included`, { included }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ['backlog'] }); },
  });

  return (
    <Card size="small" style={{ background: '#0f2340', border: '1px solid #1e3a5f' }}>
      <PlanConflictBanner issueId={p.issueId} />

      {p.hasChildren && (
        <Space orientation="vertical" style={{ width: '100%', marginBottom: 12 }}>
          <Radio.Group
            value={p.planningMode}
            onChange={(e) => modeMut.mutate(e.target.value as 'whole' | 'by_epics')}
            optionType="button"
          >
            <Radio.Button value="whole">RFA целиком</Radio.Button>
            <Radio.Button value="by_epics">По Эпикам</Radio.Button>
          </Radio.Group>
          {p.planningMode === 'by_epics' && (
            <Checkbox
              checked={p.includedInPlanning}
              onChange={(e) => incMut.mutate({ id: p.backlogItemId, included: e.target.checked })}
            >
              Включить саму RFA (для непокрытых кварталов)
            </Checkbox>
          )}
        </Space>
      )}

      {data && <HoursBreakdownTable data={data} loading={isLoading} />}

      <div style={{ marginTop: 12 }}>
        <Button onClick={() => setEditOpen(true)}>✎ Редактировать план</Button>
      </div>

      <PlanEditDrawer
        open={editOpen}
        onClose={() => setEditOpen(false)}
        issueId={p.issueId}
        issueKey={p.issueKey}
        jiraValues={p.jiraValues}
        effectiveValues={p.effectiveValues}
      />

      {p.hasChildren && p.children && p.children.length > 0 && (
        <ChildrenList
          items={p.children}
          mode={p.planningMode}
          onToggle={(child, value) => incMut.mutate({ id: child.id, included: value })}
        />
      )}
    </Card>
  );
}

function ChildrenList({
  items, mode, onToggle,
}: {
  items: ChildItem[];
  mode: 'whole' | 'by_epics';
  onToggle: (child: ChildItem, value: boolean) => void;
}) {
  return (
    <div style={{ marginTop: 12 }}>
      <div style={{ color: '#94a3b8', fontSize: 12, marginBottom: 4 }}>Дочерние Эпики</div>
      {items.map((c) => (
        <div key={c.id} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '4px 0' }}>
          {mode === 'by_epics' && (
            <Checkbox
              checked={c.included_in_planning}
              onChange={(e) => onToggle(c, e.target.checked)}
            />
          )}
          <span style={{ fontFamily: 'monospace', minWidth: 120 }}>{c.key}</span>
          <span style={{ flex: 1 }}>{c.title}</span>
        </div>
      ))}
    </div>
  );
}
