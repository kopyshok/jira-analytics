import { useCallback } from 'react';
import { Button, Empty, Segmented, Select, Skeleton, Spin } from 'antd';
import { LayoutGrid } from 'lucide-react';
import '../warm-layout.css';
import './ProjectsLayout.css';
import type { ProjectsPageState } from '../../../hooks/useProjectsPage';
import type { Portfolio } from '../../../types/projects';
import { ProjectListCard } from '../../../components/projects/ProjectListCard';
import { ProjectListFilters } from '../../../components/projects/ProjectListFilters';
import { ProjectDetailPanel } from '../../../components/projects/ProjectDetailPanel';
import { WorkTypeRings } from '../../../components/projects/plan/WorkTypeRings';
import { PortfolioSignals } from '../../../components/projects/plan/PortfolioSignals';
import { PortfolioProjectsTable } from '../../../components/projects/plan/PortfolioProjectsTable';
import { PhaseTimeline } from '../../../components/projects/plan/PhaseTimeline';
import { pluralProjects } from '../../../utils/projectsView';

/**
 * «Проекты» в скине «Тёплая» (макет C-projects): слева карточка со списком —
 * «Сводка», год и квартал, поиск, два переключателя и карточки проектов со
 * своей прокруткой; справа — сводка портфеля (итоги и стадии, сигналы,
 * таблица проектов, таймлайн) или карточка выбранного проекта. Страница
 * помещается в экран. Данные и обработчики — общие с раскладкой Aurora
 * (useProjectsPage).
 */
export default function WarmProjectsLayout({ state }: { state: ProjectsPageState }) {
  const {
    projectKey, filters, patchFilters, yearOptions,
    projects, listLoading, portfolio, portfolioLoading,
    handleSelect, showPortfolio, openProject,
  } = state;
  // Поиск отдаёт значение с задержкой и следит за обработчиком — он должен
  // быть постоянным, иначе задержка перезапускается на каждой отрисовке.
  const onSearchChange = useCallback((v: string) => patchFilters({ search: v }), [patchFilters]);

  return (
    <div className="wr-fit pjc-page">
      <div className="pjc-body">
        <aside className="wr-card pjc-side" aria-label="Список проектов">
          <div className="pjc-side-head">
            <div className="pjc-side-title">
              <h2>Проекты</h2>
              {projects && <span className="pjc-count">{projects.length}</span>}
            </div>
            <Button
              className="pjc-summary-btn"
              type={projectKey ? 'default' : 'primary'}
              block
              icon={<LayoutGrid size={16} aria-hidden />}
              aria-pressed={!projectKey}
              onClick={showPortfolio}
            >
              Сводка
            </Button>
            <div className="pjc-period">
              <label className="wr-field pjc-year">
                <span className="wr-field-label">Год</span>
                <Select
                  variant="borderless"
                  aria-label="Год"
                  value={filters.year}
                  onChange={(y) => patchFilters({ year: y })}
                  options={yearOptions}
                  popupMatchSelectWidth={false}
                />
              </label>
              <Segmented
                className="pjc-quarters"
                block
                aria-label="Квартал"
                value={filters.quarter}
                onChange={(q) => patchFilters({ quarter: Number(q) })}
                options={[1, 2, 3, 4].map((q) => ({ value: q, label: `Q${q}` }))}
              />
            </div>
            <ProjectListFilters
              compact
              search={filters.search}
              onSearchChange={onSearchChange}
              statusCategory={filters.statusCategory}
              onStatusCategoryChange={(v) => patchFilters({ statusCategory: v })}
              category={filters.category}
              onCategoryChange={(v) => patchFilters({ category: v })}
            />
          </div>

          <div className="pjc-list">
            {listLoading && Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} active paragraph={{ rows: 2 }} />
            ))}
            {!listLoading && !projects?.length && (
              <Empty description="Нет проектов" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            )}
            {!listLoading && projects?.map((item) => (
              <ProjectListCard
                compact
                key={item.key}
                item={item}
                selected={item.key === projectKey}
                onClick={() => handleSelect(item.key)}
              />
            ))}
          </div>
        </aside>

        {projectKey ? (
          <section className="pjc-main pjc-detail" aria-label="Карточка проекта">
            <ProjectDetailPanel compact projectKey={projectKey} year={filters.year} quarter={filters.quarter} />
          </section>
        ) : (
          <section className="pjc-main" aria-label="Сводка портфеля">
            <PortfolioSummary data={portfolio} isLoading={portfolioLoading} onOpenProject={openProject} />
          </section>
        )}
      </div>
    </div>
  );
}

/** Правая часть без выбранного проекта: итоги и сигналы, таблица, таймлайн. */
function PortfolioSummary({ data, isLoading, onOpenProject }: {
  data: Portfolio | undefined;
  isLoading: boolean;
  onOpenProject: (key: string) => void;
}) {
  if (isLoading || !data) {
    return <div className="wr-card pjc-empty" data-testid="portfolio-view"><Spin /></div>;
  }
  if (data.project_count === 0) {
    return (
      <div className="wr-card pjc-empty" data-testid="portfolio-view">
        <Empty description="Нет проектов за выбранный квартал" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }
  return (
    <>
      <div className="pjc-top" data-testid="portfolio-view">
        <div className="wr-card pjc-kpi-card">
          <WorkTypeRings
            compact
            countLabel={pluralProjects(data.project_count)}
            count={data.project_count}
            workTypes={data.work_types}
            externalHours={data.external_hours}
            totalPlan={data.total_plan}
            totalFact={data.total_fact}
            totalPct={data.total_pct}
          />
        </div>
        {data.signals.length > 0 && (
          <section className="wr-card pjc-signals-card" aria-label="Сигналы">
            <h2 className="rpc-card-title">Сигналы</h2>
            <PortfolioSignals compact signals={data.signals} />
          </section>
        )}
      </div>

      <section className="wr-card pjc-table-card" aria-label="Проекты портфеля">
        <PortfolioProjectsTable
          compact
          title="Проекты портфеля"
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
        />
      </section>

      <section className="wr-card pjc-tl-card" aria-label="Таймлайн портфеля">
        <PhaseTimeline
          compact
          title="Таймлайн портфеля"
          timeline={data.timeline}
          mode="by-project"
          onRowClick={onOpenProject}
        />
      </section>
    </>
  );
}
