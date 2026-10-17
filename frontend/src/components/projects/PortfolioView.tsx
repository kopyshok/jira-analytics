import React from 'react';
import { Card, Empty, Spin } from 'antd';
import type { Portfolio } from '../../types/projects';
import { WorkTypeRings } from './plan/WorkTypeRings';
import { PhaseTimeline } from './plan/PhaseTimeline';
import { PortfolioProjectsTable } from './plan/PortfolioProjectsTable';
import { PortfolioSignals } from './plan/PortfolioSignals';
import { DARK_THEME } from '../../utils/constants';
import { pluralProjects } from '../../utils/projectsView';

interface Props {
  /** Сводка приходит со страницы (useProjectsPage) — один источник с раскладками скинов. */
  data: Portfolio | undefined;
  isLoading: boolean;
  onOpenProject: (key: string) => void;
}

export const PortfolioView: React.FC<Props> = ({ data, isLoading, onOpenProject }) => {
  if (isLoading || !data) {
    return (
      <div
        data-testid="portfolio-view"
        style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      >
        <Spin size="large" />
      </div>
    );
  }

  if (data.project_count === 0) {
    return (
      <div
        data-testid="portfolio-view"
        style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      >
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
    <div
      data-testid="portfolio-view"
      style={{ flex: 1, overflowY: 'auto', padding: 16, display: 'flex', flexDirection: 'column', gap: 16 }}
    >
      <WorkTypeRings
        countLabel={pluralProjects(data.project_count)}
        count={data.project_count}
        workTypes={data.work_types}
        externalHours={data.external_hours}
        totalPlan={data.total_plan}
        totalFact={data.total_fact}
        totalPct={data.total_pct}
      />

      <Card
        size="small"
        title={<span style={{ color: 'var(--text-2, #cfd8e5)', fontSize: 13 }}>Проекты портфеля</span>}
        style={{ background: DARK_THEME.cardBg, border: '1px solid rgba(255,255,255,0.06)' }}
        styles={{ header: { borderColor: 'rgba(255,255,255,0.06)' }, body: { padding: 0 } }}
      >
        <PortfolioProjectsTable
          projects={data.projects}
          timeline={data.timeline}
          totals={{
            workTypes: data.work_types,
            externalHours: data.external_hours,
            totalPlan: data.total_plan,
            totalFact: data.total_fact,
            totalPct: data.total_pct,
          }}
          onRowClick={onOpenProject}
          maxHeight="calc(33vh + 120px)"
        />
      </Card>

      <Card
        size="small"
        title={<span style={{ color: 'var(--text-2, #cfd8e5)', fontSize: 13 }}>Таймлайн портфеля</span>}
        style={{ background: DARK_THEME.cardBg, border: '1px solid rgba(255,255,255,0.06)' }}
        styles={{ header: { borderColor: 'rgba(255,255,255,0.06)' }, body: { padding: 12 } }}
      >
        <PhaseTimeline
          timeline={data.timeline}
          mode="by-project"
          maxHeight="38vh"
          onRowClick={onOpenProject}
        />
      </Card>

      <PortfolioSignals signals={data.signals} />
    </div>
  );
};
