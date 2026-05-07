import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router';
import { Card, Col, Row, Spin } from 'antd';
import PageHeader from '../components/shared/PageHeader';
import Toolbar from '../components/work-type-report/Toolbar';
import AiHeadline from '../components/work-type-report/AiHeadline';
import KpiRow from '../components/work-type-report/KpiRow';
import EmptyState from '../components/work-type-report/EmptyState';
import ThemeDistribution from '../components/work-type-report/ThemeDistribution';
import GroupingControl from '../components/work-type-report/GroupingControl';
import HierarchyTable from '../components/work-type-report/HierarchyTable';
import { useThemeList } from '../hooks/useThemeDictionary';
import { useWorkTypeReport } from '../hooks/useWorkTypeReport';
import { useMandatoryWorkTypes } from '../hooks/useMandatoryWorkTypes';
import { useGlobalPeriod } from '../hooks/useGlobalPeriod';
import { useGlobalTeamFilter } from '../hooks/useGlobalTeamFilter';
import { DARK_THEME } from '../utils/constants';
import type { GroupingDim } from '../types/workTypeReport';

const PLACEHOLDER_STYLE: React.CSSProperties = {
  background: DARK_THEME.darkRows,
  border: `1px dashed ${DARK_THEME.border}`,
  borderRadius: 8,
  padding: '24px 20px',
  marginBottom: 16,
  color: DARK_THEME.textMuted,
  fontSize: 13,
  textAlign: 'center',
};

export default function WorkTypeReportPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { data: workTypes, isLoading: wtLoading } = useMandatoryWorkTypes();
  const { period } = useGlobalPeriod();
  const { selectedTeams } = useGlobalTeamFilter();

  const [groupingDims, setGroupingDims] = useState<GroupingDim[]>(['theme', 'issue']);
  const [highlightThemeId, setHighlightThemeId] = useState<string | null>(null);

  const activeTypes = workTypes ?? [];

  // Sync workTypeId to URL; default to first active type
  const urlWorkTypeId = searchParams.get('work_type_id');
  const workTypeId = urlWorkTypeId ?? (activeTypes[0]?.id ?? null);

  // Once we know the default, write it to URL so it's bookmarkable
  useEffect(() => {
    if (!urlWorkTypeId && activeTypes.length > 0) {
      setSearchParams(
        (prev) => {
          prev.set('work_type_id', activeTypes[0].id);
          return prev;
        },
        { replace: true },
      );
    }
  }, [urlWorkTypeId, activeTypes, setSearchParams]);

  const handleWorkTypeChange = (id: string) => {
    setSearchParams((prev) => {
      prev.set('work_type_id', id);
      return prev;
    });
  };

  // Data fetching
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

  return (
    <div>
      <PageHeader eyebrow="АНАЛИТИКА" title="Тематический отчёт" />

      {isLoading ? (
        <div style={{ display: 'grid', placeItems: 'center', minHeight: 300 }}>
          <Spin size="large" />
        </div>
      ) : isEmpty ? (
        <EmptyState workTypeId={workTypeId} />
      ) : (
        <>
          <Toolbar
            workTypeId={workTypeId ?? ''}
            onWorkTypeChange={handleWorkTypeChange}
            report={report}
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
                {/* Placeholder — Task 14: outliers + recommendation */}
                <Card style={PLACEHOLDER_STYLE as React.CSSProperties}>
                  <span>Outliers / Рекомендация — Task 14</span>
                </Card>
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
              onIssueClick={() => {
                /* Task 14: wire to IssueDrillDownDrawer */
              }}
            />
          )}
        </>
      )}
    </div>
  );
}
