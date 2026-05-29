import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router';
import { Button, Card, Col, Row, Spin } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import HelpDrawer from '../components/shared/HelpDrawer';
import workTypeReportHelp from '../../../docs/help/work-type-report.md?raw';
import Toolbar from '../components/work-type-report/Toolbar';
import { FONTS } from '../utils/constants';
import AiHeadline from '../components/work-type-report/AiHeadline';
import KpiRow from '../components/work-type-report/KpiRow';
import EmptyState from '../components/work-type-report/EmptyState';
import ThemeDistribution from '../components/work-type-report/ThemeDistribution';
import GroupingControl from '../components/work-type-report/GroupingControl';
import HierarchyTable from '../components/work-type-report/HierarchyTable';
import RecommendationCard from '../components/work-type-report/RecommendationCard';
import IssueDrillDownDrawer from '../components/work-type-report/IssueDrillDownDrawer';
import ManualReviewBlock from '../components/work-type-report/ManualReviewBlock';
import CandidatesPanel from '../components/work-type-report/CandidatesPanel';
import ThemeDictionaryDrawer from '../components/work-type-report/ThemeDictionaryDrawer';
import { useThemeList } from '../hooks/useThemeDictionary';
import { useWorkTypeReport, useBuildWorkTypeReportStream } from '../hooks/useWorkTypeReport';
import { useLayoutList } from '../hooks/useWorkTypeReportLayouts';
import { useMandatoryWorkTypes } from '../hooks/useMandatoryWorkTypes';
import { useGlobalPeriod } from '../hooks/useGlobalPeriod';
import { useGlobalTeamFilter } from '../hooks/useGlobalTeamFilter';
import { DARK_THEME } from '../utils/constants';
import type { GroupingDim, Theme } from '../types/workTypeReport';
import BuildProgressModal from '../components/work-type-report/BuildProgressModal';
import { AiOffNotice } from '../components/shared/AiOffNotice';
import { useAiEnabled } from '../hooks/useAiEnabled';

/** Returns ISO date bounds for a quarter (or a specific month). */
function periodBounds(year: number, quarter: number, month?: number): { start: string; end: string } {
  if (month != null) {
    const mm = String(month).padStart(2, '0');
    const lastDay = new Date(year, month, 0).getDate();
    return { start: `${year}-${mm}-01`, end: `${year}-${mm}-${lastDay}` };
  }
  const qStartMonth = (quarter - 1) * 3 + 1;
  const qEndMonth = qStartMonth + 2;
  const lastDay = new Date(year, qEndMonth, 0).getDate();
  return {
    start: `${year}-${String(qStartMonth).padStart(2, '0')}-01`,
    end: `${year}-${String(qEndMonth).padStart(2, '0')}-${lastDay}`,
  };
}

/** Find which theme (and contribution) an issue belongs to in the snapshot. */
function findIssueClassification(
  themes: Theme[],
  issueId: string,
): { themeName: string | null; contribution: string | null } {
  for (const t of themes) {
    const found = t.issues.find((i) => i.issue_id === issueId);
    if (found) {
      return { themeName: t.name ?? null, contribution: found.contribution ?? null };
    }
  }
  return { themeName: null, contribution: null };
}

export default function WorkTypeReportPage() {
  const { enabled: aiEnabled, isLoading: aiStatusLoading } = useAiEnabled();
  if (!aiStatusLoading && !aiEnabled) {
    return (
      <AiOffNotice
        title="Тематический отчёт выключен администратором"
        description="Раздел полностью построен на ИИ. Чтобы открыть, обратитесь к администратору сервиса для включения ИИ."
      />
    );
  }
  return <WorkTypeReportPageInner />;
}

function WorkTypeReportPageInner() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: workTypes, isLoading: wtLoading } = useMandatoryWorkTypes();
  const { period } = useGlobalPeriod();
  const { selectedTeams } = useGlobalTeamFilter();

  const [groupingDims, setGroupingDims] = useState<GroupingDim[]>(['theme', 'issue']);
  const appliedDefaultRef = useRef<string | null>(null);
  const [highlightThemeId, setHighlightThemeId] = useState<string | null>(null);
  const [drillIssue, setDrillIssue] = useState<{ id: string; key: string } | null>(null);
  const [dictionaryDrawer, setDictionaryDrawer] = useState<{ open: boolean; tab: 'active' | 'archived' | 'candidates' }>({ open: false, tab: 'active' });
  const [progressModalOpen, setProgressModalOpen] = useState(false);
  const [buildDone, setBuildDone] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const buildStream = useBuildWorkTypeReportStream();

  const activeTypes = useMemo(() => workTypes ?? [], [workTypes]);

  // Sync workTypeId to URL; default to last-used (localStorage) → first active type
  const urlWorkTypeId = searchParams.get('work_type_id');
  const storedWorkTypeId = typeof window !== 'undefined'
    ? window.localStorage.getItem('workTypeReport.work_type_id')
    : null;
  const fallbackId = (() => {
    if (storedWorkTypeId && activeTypes.some((t) => t.id === storedWorkTypeId)) {
      return storedWorkTypeId;
    }
    return activeTypes[0]?.id ?? null;
  })();
  const workTypeId = urlWorkTypeId ?? fallbackId;

  useEffect(() => {
    if (!urlWorkTypeId && fallbackId) {
      setSearchParams(
        (prev) => {
          prev.set('work_type_id', fallbackId);
          return prev;
        },
        { replace: true },
      );
    }
  }, [urlWorkTypeId, fallbackId, setSearchParams]);

  // Persist active selection so navigating away and back keeps it
  useEffect(() => {
    if (workTypeId) {
      window.localStorage.setItem('workTypeReport.work_type_id', workTypeId);
    }
  }, [workTypeId]);

  const handleWorkTypeChange = (id: string) => {
    setSearchParams((prev) => {
      prev.set('work_type_id', id);
      return prev;
    });
  };

  // Data fetching
  const layoutListQuery = useLayoutList(workTypeId);
  const themesQuery = useThemeList(workTypeId, false);
  const reportQuery = useWorkTypeReport(
    {
      work_type_id: workTypeId ?? '',
      year: period.year,
      quarter: period.quarter,
      month: period.month ?? null,
      teams: selectedTeams,
    },
    { enabled: !!workTypeId },
  );

  const themes = themesQuery.data?.themes ?? [];
  const report = reportQuery.data;

  const isLoading =
    wtLoading ||
    (themesQuery.isLoading && !themesQuery.data) ||
    (reportQuery.isLoading && !reportQuery.data);

  const isEmpty = themes.length === 0 && !report;

  // Auto-apply default layout once per work-type-id
  useEffect(() => {
    if (!workTypeId || appliedDefaultRef.current === workTypeId) return;
    const def = layoutListQuery.data?.find((l) => l.is_default);
    if (def) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setGroupingDims(def.grouping_dims);
      appliedDefaultRef.current = workTypeId;
    }
  }, [workTypeId, layoutListQuery.data]);

  const { start: periodStart, end: periodEnd } = useMemo(
    () => periodBounds(period.year, period.quarter, period.month),
    [period.year, period.quarter, period.month],
  );

  // Drill-issue classification info derived from snapshot
  const drillClassification = useMemo(() => {
    if (!drillIssue || !report) return { themeName: null, contribution: null };
    return findIssueClassification(report.data.themes, drillIssue.id);
  }, [drillIssue, report]);

  const drillNeedsManualClassify = useMemo(() => {
    if (!drillIssue || !report) return false;
    return report.data.manual_review_required.some((m) => m.issue_id === drillIssue.id);
  }, [drillIssue, report]);

  const handleIssueClick = (issueId: string, issueKey: string) => {
    setDrillIssue({ id: issueId, key: issueKey });
  };

  const _startBuild = (forceRefresh: boolean) => {
    if (!workTypeId) return;
    setBuildDone(false);
    setProgressModalOpen(true);
    void buildStream.start(
      {
        work_type_id: workTypeId,
        year: period.year,
        quarter: period.quarter,
        month: period.month ?? null,
        teams: selectedTeams.length > 0 ? selectedTeams : undefined,
        force_refresh: forceRefresh,
      },
      () => setBuildDone(true),
    );
  };

  const handleRebuild = () => _startBuild(true);
  const handleBuild = () => _startBuild(false);

  return (
    <div>
      {/* Compact page header — eyebrow + title in ~40px; no PageHeader block */}
      <div
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: 12,
          marginBottom: 12,
        }}
      >
        <span
          style={{
            fontSize: 11,
            letterSpacing: '0.14em',
            textTransform: 'uppercase',
            color: DARK_THEME.cyanPrimary,
            fontWeight: 600,
          }}
        >
          АНАЛИТИКА
        </span>
        <span
          style={{
            fontSize: 22,
            fontFamily: FONTS.display,
            fontWeight: 600,
            color: DARK_THEME.textPrimary,
            lineHeight: 1.2,
          }}
        >
          Тематический отчёт
        </span>
        <Button
          type="text"
          size="small"
          icon={<QuestionCircleOutlined />}
          onClick={() => setHelpOpen(true)}
          title="Справка по разделу"
          style={{ marginLeft: 'auto' }}
        >
          Справка
        </Button>
      </div>
      <HelpDrawer
        open={helpOpen}
        onClose={() => setHelpOpen(false)}
        title="Отчёт по видам работ"
        content={workTypeReportHelp}
        imageBase="/help-assets/"
      />

      {isLoading ? (
        <div style={{ display: 'grid', placeItems: 'center', minHeight: 300 }}>
          <Spin size="large" />
        </div>
      ) : isEmpty ? (
        <EmptyState workTypeId={workTypeId} onBuild={handleBuild} isBuilding={buildStream.state.isRunning} />
      ) : (
        <>
          <Toolbar
            workTypeId={workTypeId ?? ''}
            onWorkTypeChange={handleWorkTypeChange}
            report={report}
            onOpenDictionary={() => setDictionaryDrawer({ open: true, tab: 'active' })}
            onRebuild={handleRebuild}
            isRebuilding={buildStream.state.isRunning}
          />
          {report && (
            <>
              <AiHeadline report={report} />
              <KpiRow totals={report.data.totals} />
            </>
          )}

          {report && (
            <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
              <Col xs={24} lg={10}>
                <ThemeDistribution
                  themes={report.data.themes}
                  totalHours={report.data.totals.hours}
                  onThemeClick={setHighlightThemeId}
                />
              </Col>
              <Col xs={24} lg={14}>
                <Card
                  style={{
                    background: DARK_THEME.cardBg,
                    border: `1px solid ${DARK_THEME.border}`,
                    borderRadius: 8,
                  }}
                  styles={{ body: { padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 12 } }}
                >
                  {report.data.recommendation?.text ? (
                    <RecommendationCard recommendation={report.data.recommendation} />
                  ) : (
                    <div style={{ color: DARK_THEME.textMuted, fontSize: 13, textAlign: 'center', padding: '12px 0' }}>
                      Рекомендаций нет
                    </div>
                  )}
                </Card>

                {report.data.candidates.length > 0 && (
                  <CandidatesPanel
                    candidates={report.data.candidates}
                    onOpenDrawer={() => setDictionaryDrawer({ open: true, tab: 'candidates' })}
                  />
                )}
              </Col>
            </Row>
          )}

          {report && (
            <GroupingControl
              workTypeId={workTypeId!}
              groupingDims={groupingDims}
              onChange={setGroupingDims}
            />
          )}

          {report && (
            <HierarchyTable
              themes={report.data.themes}
              groupingDims={groupingDims}
              highlightThemeId={highlightThemeId}
              onIssueClick={handleIssueClick}
            />
          )}

          {report && (
            <ManualReviewBlock
              items={report.data.manual_review_required}
              workTypeId={workTypeId ?? ''}
              themes={themes}
            />
          )}
        </>
      )}

      {/* Drill-down drawer — rendered at page level, outside the conditional blocks */}
      <IssueDrillDownDrawer
        open={!!drillIssue}
        issueId={drillIssue?.id ?? null}
        issueKey={drillIssue?.key ?? null}
        workTypeId={workTypeId ?? ''}
        periodStart={periodStart}
        periodEnd={periodEnd}
        onClose={() => setDrillIssue(null)}
        themeName={drillClassification.themeName}
        contribution={drillClassification.contribution}
        needsManualClassify={drillNeedsManualClassify}
      />

      {/* Theme dictionary drawer */}
      <ThemeDictionaryDrawer
        open={dictionaryDrawer.open}
        workTypeId={workTypeId ?? ''}
        initialTab={dictionaryDrawer.tab}
        candidates={report?.data.candidates ?? []}
        snapshotId={report?.snapshot_id ?? null}
        onClose={() => setDictionaryDrawer((s) => ({ ...s, open: false }))}
      />

      {/* SSE build progress modal */}
      <BuildProgressModal
        open={progressModalOpen}
        state={buildStream.state}
        showDone={buildDone}
        onCancel={() => {
          buildStream.cancel();
          setProgressModalOpen(false);
        }}
        onClose={() => setProgressModalOpen(false)}
      />
    </div>
  );
}
