import { Row, Col } from 'antd';
import ProjectsWidget from '../components/dashboard/ProjectsWidget';
import NormWorkWidget from '../components/dashboard/NormWorkWidget';
import CategoryWidget from '../components/dashboard/CategoryWidget';
import { useDashboardProjects, useDashboardNormWork, useDashboardCategories } from '../hooks/useAnalytics';
import type { QuarterPeriod } from '../types/api';
import { useGlobalTeamFilter } from '../hooks/useGlobalTeamFilter';
import { useGlobalPeriod } from '../hooks/useGlobalPeriod';

export default function DashboardPage() {
  const { period: globalPeriod } = useGlobalPeriod();
  const period: QuarterPeriod = {
    year: globalPeriod.year,
    quarter: globalPeriod.quarter as 1 | 2 | 3 | 4,
    month: globalPeriod.month,
  };
  const { queryParams: teamParams } = useGlobalTeamFilter();

  const { data: projects, isLoading: projLoading } = useDashboardProjects(period);
  const { data: normWork, isLoading: normLoading } = useDashboardNormWork(period, teamParams);
  const { data: categories, isLoading: catLoading } = useDashboardCategories(period, teamParams);

  return (
    <div>
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24}>
          <ProjectsWidget data={projects} loading={projLoading} />
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24}>
          <NormWorkWidget data={normWork} loading={normLoading} />
        </Col>
      </Row>

      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24}>
          <CategoryWidget data={categories} loading={catLoading} />
        </Col>
      </Row>

    </div>
  );
}
