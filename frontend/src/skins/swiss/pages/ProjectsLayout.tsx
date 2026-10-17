import { Empty, Spin } from 'antd';
import type { ProjectsPageModel } from '../../../hooks/useProjectsPage';
import { usePortfolioForFilters } from '../../../hooks/useProjectsPage';
import { ProjectsList } from '../../../components/projects/ProjectsList';
import { ProjectListFilters } from '../../../components/projects/ProjectListFilters';
import { projectYearOptions } from '../../../components/projects/projectYears';
import { ProjectDetailPanel } from '../../../components/projects/ProjectDetailPanel';
import { WorkTypeRings } from '../../../components/projects/plan/WorkTypeRings';
import { PortfolioSignals } from '../../../components/projects/plan/PortfolioSignals';
import { PortfolioProjectsTable } from '../../../components/projects/plan/PortfolioProjectsTable';
import { PhaseTimeline } from '../../../components/projects/plan/PhaseTimeline';
import { BlockHead, PassSection, Passport, SwissData, SwissPage } from '../components/Passport';
import './projects.css';

/** «проект / проекта / проектов». */
function projectsWord(n: number): string {
  if (n % 100 >= 11 && n % 100 <= 14) return 'проектов';
  const last = n % 10;
  if (last === 1) return 'проект';
  if (last >= 2 && last <= 4) return 'проекта';
  return 'проектов';
}

const num = (v: number) => Math.round(v).toLocaleString('ru-RU');

/**
 * «Проекты» в обложке «Швейцарская»: паспорт (сводные цифры портфеля и
 * отбор столбиком), колонка «1.1 Проекты» строками, справа сводка портфеля
 * по стадиям, сигналы, таблица проектов и таймлайн; выбран проект —
 * справа его карточка.
 */
export default function SwissProjectsLayout({ vm }: { vm: ProjectsPageModel }) {
  const { key, filters, setFilters, handleSelect, showPortfolio, openProject } = vm;
  const { data, isLoading } = usePortfolioForFilters(filters);
  const patch = (part: Partial<typeof filters>) => setFilters({ ...filters, ...part });
  const pctTone = data?.total_pct == null ? '' : data.total_pct > 110 ? ' is-over' : data.total_pct >= 70 ? ' is-ok' : '';

  return (
    <SwissPage className="sw-pj">
      <Passport
        eyebrow="Обзор / Проекты"
        title="Проекты"
        subtitle="Сводка портфеля на квартал: сколько часов потрачено, где перегруз, как проекты ложатся по срокам."
      >
        <div className="sw-pj-figures">
          <div className="sw-pj-fig-inline">
            <span className="sw-pj-big">{data ? data.project_count : '—'}</span>
            <span className="sw-pj-cap">{data ? projectsWord(data.project_count) : 'проектов'}</span>
          </div>
          <div>
            <div className="sw-pj-mid">
              {data ? `${num(data.total_fact)} / ${data.total_plan == null ? '—' : num(data.total_plan)} ч` : '—'}
            </div>
            <div className="sw-pj-cap">{data?.total_plan == null ? 'план не заведён' : 'всего факт / план'}</div>
          </div>
          <div className="sw-pj-fig-inline">
            <span className={`sw-pj-big${pctTone}`}>{data?.total_pct == null ? '—' : `${data.total_pct}%`}</span>
            <span className="sw-pj-cap">загрузка · норма ≥ 70%</span>
          </div>
        </div>

        <PassSection eyebrow="Отбор проектов">
          <ProjectListFilters
            variant="stack"
            year={filters.year}
            quarter={filters.quarter}
            yearOptions={projectYearOptions()}
            onYearChange={(y) => patch({ year: y })}
            onQuarterChange={(q) => patch({ quarter: q })}
            search={filters.search}
            onSearchChange={(v) => patch({ search: v })}
            statusCategory={filters.statusCategory}
            onStatusCategoryChange={(v) => patch({ statusCategory: v })}
            category={filters.category}
            onCategoryChange={(v) => patch({ category: v })}
          />
        </PassSection>
      </Passport>

      <SwissData className="sw-pj-data">
        <ProjectsList
          variant="column"
          selectedKey={key ?? null}
          onSelect={handleSelect}
          filters={filters}
          onFiltersChange={setFilters}
          onShowPortfolio={showPortfolio}
        />

        <div className="sw-pj-main">
          {key ? (
            <div className="sw-pj-detail">
              <ProjectDetailPanel projectKey={key} year={filters.year} quarter={filters.quarter} />
            </div>
          ) : isLoading || !data ? (
            <div className="sw-pj-loading" data-testid="portfolio-view"><Spin /></div>
          ) : data.project_count === 0 ? (
            <div className="sw-pj-loading" data-testid="portfolio-view">
              <Empty description="Нет проектов за выбранный квартал" image={Empty.PRESENTED_IMAGE_SIMPLE} />
            </div>
          ) : (
            <div className="sw-pj-portfolio" data-testid="portfolio-view">
              <section className="sw-block sw-pj-summary">
                <BlockHead num="1.2" title="Сводка портфеля" size="lg" meta="факт / план по стадиям" />
                <WorkTypeRings
                  variant="bars"
                  workTypes={data.work_types}
                  externalHours={data.external_hours}
                  totalPlan={data.total_plan}
                  totalFact={data.total_fact}
                  totalPct={data.total_pct}
                />
                {data.signals.length > 0 && (
                  <div className="sw-pj-signals">
                    <span className="sw-pj-signals-label">Сигналы</span>
                    <PortfolioSignals signals={data.signals} />
                  </div>
                )}
              </section>

              <section className="sw-block sw-pj-table">
                <BlockHead num="1.3" title="Проекты портфеля" size="lg" />
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
                  onRowClick={openProject}
                  maxHeight="max(220px, calc(100vh - 700px))"
                />
              </section>

              <section className="sw-block sw-pj-timeline">
                <BlockHead num="1.4" title="Таймлайн портфеля" size="lg" />
                <PhaseTimeline
                  timeline={data.timeline}
                  mode="by-project"
                  todayCaption
                  maxHeight="max(160px, calc(100vh - 880px))"
                  onRowClick={openProject}
                />
              </section>
            </div>
          )}
        </div>
      </SwissData>
    </SwissPage>
  );
}
