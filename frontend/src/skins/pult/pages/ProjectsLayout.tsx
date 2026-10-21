import { Empty, Select, Spin } from 'antd';
import { InfoCircleOutlined, WarningOutlined } from '@ant-design/icons';
import { ProjectsList } from '../../../components/projects/ProjectsList';
import { ProjectDetailPanel } from '../../../components/projects/ProjectDetailPanel';
import { ProjectListFilters } from '../../../components/projects/ProjectListFilters';
import { PortfolioProjectsTable } from '../../../components/projects/plan/PortfolioProjectsTable';
import { PhaseTimeline } from '../../../components/projects/plan/PhaseTimeline';
import { StarRating } from '../../../components/projects/shared/StarRating';
import {
  avgProjectRating, CATEGORY_LABEL, formatProjectMonth, pluralProjects, projectQueryParams, STATUS_CATEGORY_LABEL,
} from '../../../components/projects/projectsShared';
import { usePortfolio, useProjectsList } from '../../../hooks/useProjects';
import type { ProjectListItem, ProjectListFiltersState } from '../../../types/projects';
import type { ProjectsPageState } from '../../../pages/ProjectsPage';
import { PULT_PHASE_COLORS, PULT_SIGNAL } from '../palette';
import { PcField, PcRow, PcTitle, PModule, PultScreen } from '../ui';

const CURRENT_YEAR = new Date().getFullYear();
const nf = (v: number) => Math.round(v).toLocaleString('ru-RU');

const STATUS_DOT: Record<string, string> = {
  indeterminate: PULT_SIGNAL.blue,
  done: PULT_SIGNAL.green,
  new: PULT_SIGNAL.grey,
};

function PultProjectCard({ item, selected, onClick }: { item: ProjectListItem; selected: boolean; onClick: () => void }) {
  const rating = avgProjectRating(item);
  return (
    <div
      className={`pp-card${selected ? ' is-selected' : ''}`}
      data-testid="project-card"
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      onClick={onClick}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick();
        }
      }}
    >
      <span className="pp-card-top">
        <i className="p-dot" style={{ background: STATUS_DOT[item.status_category ?? ''] ?? PULT_SIGNAL.grey }} />
        <span className="num pp-key">{item.key}</span>
        {item.status_category && (
          <span className="pc-cap pp-status">{STATUS_CATEGORY_LABEL[item.status_category] ?? item.status_category}</span>
        )}
      </span>
      <span className="pp-title">{item.summary}</span>
      <span className="num pp-period">{formatProjectMonth(item.period_start)} – {formatProjectMonth(item.period_end)}</span>
      <span className="pp-meta">
        <span><b className="num">{nf(item.total_hours)}</b> ч</span>
        <span><b className="num">{item.child_count}</b> задач</span>
        <span><b className="num">{item.employee_count}</b> участн.</span>
        <span className="pc-cap pp-cat">{CATEGORY_LABEL[item.category] ?? item.category}</span>
      </span>
      {rating != null && (
        <span className="pp-rating"><StarRating value={rating} size={13} /> <span className="num">{rating} из 5</span></span>
      )}
    </div>
  );
}

/** Сводка портфеля, сигналы, таблица и таймлайн — те же данные, что у сводки Aurora. */
function PortfolioModules({ filters, onOpen }: { filters: ProjectListFiltersState; onOpen: (key: string) => void }) {
  const { data, isLoading } = usePortfolio(projectQueryParams(filters));
  if (isLoading || !data) return <div className="pm pp-right-empty"><Spin /></div>;
  if (data.project_count === 0) {
    return (
      <div className="pm pp-right-empty">
        <Empty description="Нет проектов за выбранный квартал" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }
  const pct = data.total_pct;
  const pctDot = pct == null ? PULT_SIGNAL.grey : pct > 110 ? PULT_SIGNAL.red : pct >= 70 ? PULT_SIGNAL.green : PULT_SIGNAL.amber;
  return (
    <div className="pp-right">
      <div className="pp-row">
        <PModule title="Сводка портфеля" className="pp-summary">
          <div className="pp-screens">
            <div className="pp-screen">
              <span className="pc-cap">Проектов</span>
              <b className="num pp-big">{data.project_count}</b>
              <span className="pp-sub" title={`${data.project_count} ${pluralProjects(data.project_count)}`}>в портфеле</span>
            </div>
            <div className="pp-screen">
              <span className="pc-cap">Факт / план, ч</span>
              <b className="num pp-big">{nf(data.total_fact)} <span className="pp-slash">/</span> {data.total_plan == null ? '—' : nf(data.total_plan)}</b>
              <span className="pp-sub">{data.total_plan == null ? 'план не заведён' : 'всего факт / план'}</span>
            </div>
            <div className="pp-screen pp-load">
              <span className="pc-cap">Загрузка</span>
              <span className="pp-load-v"><i className="p-dot" style={{ background: pctDot, width: 10, height: 10 }} /><b className="num pp-big">{pct == null ? '—' : `${pct}%`}</b></span>
              <span className="pp-meter">
                <i style={{ width: `${Math.min(pct ?? 0, 120) / 1.2}%`, background: pctDot }} />
                <u style={{ left: `${70 / 1.2}%` }} />
                <u style={{ left: `${110 / 1.2}%` }} />
              </span>
              <span className="num pp-sub">норма 70–110%</span>
            </div>
            <span className="pp-vsep" aria-hidden="true" />
            <div className="pp-wts">
              {data.work_types.map((wt) => {
                const over = wt.pct != null && wt.pct > 110;
                return (
                  <div key={wt.code} className="pp-screen pp-wt">
                    <span className="pc-cap"><i className="pp-sq" style={{ background: PULT_PHASE_COLORS[wt.code] }} />{wt.label}</span>
                    <b className="num">{nf(wt.fact_hours)} / {nf(wt.plan_hours)} ч</b>
                    <span className="pp-wt-bar">
                      <span className="pp-meter is-thin">
                        <i style={{ width: `${Math.min(wt.pct ?? 0, 100)}%`, background: over ? PULT_SIGNAL.red : (wt.pct ?? 0) < 50 ? PULT_SIGNAL.amber : '#8C897F' }} />
                      </span>
                      <b className="num">{wt.pct == null ? '—' : `${wt.pct}%`}</b>
                    </span>
                  </div>
                );
              })}
              <div className="pp-screen pp-wt" title={data.external_hours > 0 ? 'Часы сотрудников не из команды — вне плана и факта' : undefined}>
                <span className="pc-cap"><i className="pp-sq is-hollow" />Внешние</span>
                <b className="num">{nf(data.external_hours)} ч</b>
                <span className="pp-sub">вне плана</span>
              </div>
            </div>
          </div>
        </PModule>
        <PModule title="Сигналы" className="pp-signals">
          {data.signals.length === 0 && <div className="pm-empty">Сигналов нет</div>}
          <div className="pp-signal-list" data-testid="portfolio-signals">
            {data.signals.map((s) => (
              <div key={s.kind} className="pp-signal">
                {s.severity === 'warn'
                  ? <WarningOutlined className="pp-sig-ico is-warn" />
                  : <InfoCircleOutlined className="pp-sig-ico is-info" />}
                <span className="pp-sig-text">{s.text}</span>
                <span className={`pc-cap pp-sig-tag${s.severity === 'warn' ? ' is-warn' : ''}`}>
                  {s.severity === 'warn' ? 'Предупреждение' : 'Инфо'}
                </span>
              </div>
            ))}
          </div>
        </PModule>
      </div>

      <PModule title="Проекты портфеля" className="pp-table">
        <div className="pm-screen pp-table-screen">
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
            onRowClick={onOpen}
            maxHeight="calc(33vh - 40px)"
          />
        </div>
      </PModule>

      <PModule title="Таймлайн портфеля" className="pp-timeline">
        <div className="pm-screen pp-timeline-screen">
          <PhaseTimeline timeline={data.timeline} mode="by-project" onRowClick={onOpen} fill />
        </div>
      </PModule>
    </div>
  );
}

/**
 * «Проекты» в обложке «Пульт» (D-projects): панель с отборами, список проектов,
 * справа — сводка портфеля (без выбранного проекта) или карточка проекта.
 */
export default function PultProjectsLayout({ page }: { page: ProjectsPageState }) {
  const { selectedKey, filters, setFilters, handleSelect, showPortfolio, openProject } = page;
  const patch = (part: Partial<ProjectListFiltersState>) => setFilters({ ...filters, ...part });
  const { data: projects } = useProjectsList(projectQueryParams(filters));
  const yearOptions = Array.from({ length: 5 }, (_, i) => {
    const y = CURRENT_YEAR - 1 + i;
    return { value: y, label: String(y) };
  });

  const panel = (
    <PcRow className="pp-panel">
      <PcTitle eyebrow="Обзор / Проекты" title="Проекты" count={projects?.length ?? undefined} />
      <span className="pp-panel-sep" aria-hidden="true" />
      <PcField label="Год">
        <Select value={filters.year} onChange={(y) => patch({ year: y })} options={yearOptions} style={{ width: 100 }} />
      </PcField>
      <PcField label="Квартал">
        <span className="pp-quarters" role="group" aria-label="Квартал">
          {([1, 2, 3, 4] as const).map((q) => (
            <button
              key={q}
              type="button"
              data-testid="projects-quarter-tag"
              data-quarter={q}
              aria-pressed={filters.quarter === q}
              className={`pp-q${filters.quarter === q ? ' is-on' : ''}`}
              onClick={() => patch({ quarter: q })}
            >
              Q{q}
            </button>
          ))}
        </span>
      </PcField>
      <ProjectListFilters
        variant="panel"
        search={filters.search}
        onSearchChange={(v) => patch({ search: v })}
        statusCategory={filters.statusCategory}
        onStatusCategoryChange={(v) => patch({ statusCategory: v })}
        category={filters.category}
        onCategoryChange={(v) => patch({ category: v })}
      />
    </PcRow>
  );

  return (
    <PultScreen panel={panel} bodyClassName="pp-pult">
      <PModule
        title="Проекты"
        className="pp-list"
        extra={<span className="pm-push pc-count is-small">{projects?.length ?? '—'}</span>}
      >
        <button
          type="button"
          className={`pp-summary-key${selectedKey ? '' : ' is-on'}`}
          aria-pressed={!selectedKey}
          onClick={showPortfolio}
        >
          <i className="p-dot" />Сводка
          <span className="pc-cap">{selectedKey ? 'вернуться к сводке' : 'проект не выбран'}</span>
        </button>
        <ProjectsList
          docked
          selectedKey={selectedKey}
          onSelect={handleSelect}
          filters={filters}
          onFiltersChange={setFilters}
          onShowPortfolio={showPortfolio}
          renderItem={(item, selected, onClick) => (
            <PultProjectCard item={item} selected={selected} onClick={onClick} />
          )}
        />
      </PModule>

      {selectedKey ? (
        <section className="pm pp-detail" aria-label="Проект">
          <ProjectDetailPanel projectKey={selectedKey} year={filters.year} quarter={filters.quarter} />
        </section>
      ) : (
        <PortfolioModules filters={filters} onOpen={openProject} />
      )}
    </PultScreen>
  );
}
