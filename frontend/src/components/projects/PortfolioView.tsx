import React from 'react';
import { Card, Empty, Spin } from 'antd';
import { useNavigate } from 'react-router';
import { usePortfolio } from '../../hooks/useProjects';
import type { ProjectListFiltersState } from '../../types/projects';
import { WorkTypeRings } from './plan/WorkTypeRings';
import { PhaseTimeline } from './plan/PhaseTimeline';
import { PortfolioSignals } from './plan/PortfolioSignals';
import { DARK_THEME } from '../../utils/constants';

export const PortfolioView: React.FC<{ filters: ProjectListFiltersState }> = ({ filters }) => {
  const navigate = useNavigate();
  const { data, isLoading } = usePortfolio({
    search: filters.search || undefined,
    status_category: filters.statusCategory || undefined,
    category: filters.category || undefined,
    year: filters.year,
    quarter: filters.quarter,
  });

  if (isLoading || !data) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Spin size="large" />
      </div>
    );
  }

  if (data.project_count === 0) {
    return (
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Empty
          description={
            <span style={{ color: DARK_THEME.textMuted }}>Нет проектов за выбранный квартал</span>
          }
          image={Empty.PRESENTED_IMAGE_SIMPLE}
        />
      </div>
    );
  }

  return (
    <div style={{ flex: 1, overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}>
      <WorkTypeRings
        countLabel="проектов"
        count={data.project_count}
        workTypes={data.work_types}
        externalHours={data.external_hours}
        totalPlan={data.total_plan}
        totalFact={data.total_fact}
        totalPct={data.total_pct}
      />

      <Card
        size="small"
        title={<span style={{ color: 'var(--text-2, #cfd8e5)', fontSize: 13 }}>Таймлайн портфеля</span>}
        style={{ background: DARK_THEME.cardBg, border: '1px solid rgba(255,255,255,0.06)' }}
        styles={{ header: { borderColor: 'rgba(255,255,255,0.06)' }, body: { padding: 12 } }}
      >
        <PhaseTimeline
          timeline={data.timeline}
          mode="by-project"
          onRowClick={(key) => navigate(`/projects/${encodeURIComponent(key)}`)}
        />
      </Card>

      <PortfolioSignals signals={data.signals} />
    </div>
  );
};
