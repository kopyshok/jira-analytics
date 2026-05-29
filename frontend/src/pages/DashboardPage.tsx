import { useState } from 'react';
import { Row, Col, Button } from 'antd';
import { QuestionCircleOutlined } from '@ant-design/icons';
import ProjectsWidget from '../components/dashboard/ProjectsWidget';
import NormWorkWidget from '../components/dashboard/NormWorkWidget';
import CategoryWidget from '../components/dashboard/CategoryWidget';
import HelpDrawer from '../components/shared/HelpDrawer';
import dashboardHelp from '../../../docs/help/dashboard.md?raw';
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
  const [helpOpen, setHelpOpen] = useState(false);

  const { data: projects, isLoading: projLoading } = useDashboardProjects(period);
  const { data: normWork, isLoading: normLoading } = useDashboardNormWork(period, teamParams);
  const { data: categories, isLoading: catLoading } = useDashboardCategories(period, teamParams);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 8 }}>
        <Button
          type="text"
          icon={<QuestionCircleOutlined />}
          onClick={() => setHelpOpen(true)}
          title="Справка по разделу"
        >
          Справка
        </Button>
      </div>
      <HelpDrawer
        open={helpOpen}
        onClose={() => setHelpOpen(false)}
        title="Главная (Dashboard)"
        content={dashboardHelp}
        imageBase="/help-assets/"
      />

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
