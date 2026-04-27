import { useState } from 'react';
import { Row, Col, Space } from 'antd';
import QuarterPicker from '../components/shared/QuarterPicker';
import FactFilterBar from '../components/dashboard/FactFilterBar';
import ExportButtons from '../components/shared/ExportButtons';
import ProjectsWidget from '../components/dashboard/ProjectsWidget';
import NormWorkWidget from '../components/dashboard/NormWorkWidget';
import CategoryWidget from '../components/dashboard/CategoryWidget';
import { useDashboardProjects, useDashboardNormWork, useDashboardCategories } from '../hooks/useAnalytics';
import { downloadAnalyticsXlsx, downloadAnalyticsPdf } from '../api/exports';
import { currentQuarterPeriod } from '../types/api';
import type { QuarterPeriod } from '../types/api';
import { useFactFilter } from '../hooks/useFactFilter';

export default function DashboardPage() {
  const [period, setPeriod] = useState<QuarterPeriod>(currentQuarterPeriod);
  const { queryParams: teamParams } = useFactFilter();

  const { data: projects, isLoading: projLoading } = useDashboardProjects(period);
  const { data: normWork, isLoading: normLoading } = useDashboardNormWork(period);
  const { data: categories, isLoading: catLoading } = useDashboardCategories(period);

  return (
    <div>
      <Space wrap style={{ marginBottom: 24 }}>
        <QuarterPicker value={period} onChange={setPeriod} />
        <FactFilterBar />
        <ExportButtons
          onXlsx={() => downloadAnalyticsXlsx(undefined, undefined, teamParams)}
          onPdf={() => downloadAnalyticsPdf(undefined, undefined, teamParams)}
        />
      </Space>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24}>
          <ProjectsWidget data={projects} loading={projLoading} />
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} lg={12}>
          <NormWorkWidget data={normWork} loading={normLoading} />
        </Col>
        <Col xs={24} lg={12}>
          <CategoryWidget data={categories} loading={catLoading} />
        </Col>
      </Row>

    </div>
  );
}
