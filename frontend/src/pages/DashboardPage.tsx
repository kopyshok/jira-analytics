import { useState } from 'react';
import { Row, Col, App, Space, Button, Collapse, Spin, Table, Tag } from 'antd';
import { SyncOutlined } from '@ant-design/icons';
import PageHeader from '../components/shared/PageHeader';
import QuarterPicker from '../components/shared/QuarterPicker';
import FactFilterBar from '../components/dashboard/FactFilterBar';
import ExportButtons from '../components/shared/ExportButtons';
import ProjectsWidget from '../components/dashboard/ProjectsWidget';
import NormWorkWidget from '../components/dashboard/NormWorkWidget';
import CategoryWidget from '../components/dashboard/CategoryWidget';
import { useSyncStatus, useSyncMutation } from '../hooks/useSync';
import { useDashboardProjects, useDashboardNormWork, useDashboardCategories } from '../hooks/useAnalytics';
import { downloadAnalyticsXlsx, downloadAnalyticsPdf } from '../api/exports';
import { currentQuarterPeriod } from '../types/api';
import type { QuarterPeriod, SyncStatusResponse } from '../types/api';
import { useFactFilter } from '../hooks/useFactFilter';
import { formatDate } from '../utils/format';

export default function DashboardPage() {
  const { notification } = App.useApp();
  const [period, setPeriod] = useState<QuarterPeriod>(currentQuarterPeriod);
  const { queryParams: teamParams } = useFactFilter();
  const syncFull = useSyncMutation('full');
  const { data: syncStatus, isLoading: syncLoading } = useSyncStatus();

  const { data: projects, isLoading: projLoading } = useDashboardProjects(period);
  const { data: normWork, isLoading: normLoading } = useDashboardNormWork(period);
  const { data: categories, isLoading: catLoading } = useDashboardCategories(period);

  const subtitle = period.month
    ? `${period.year} Q${period.quarter} · месяц ${period.month}`
    : `${period.year} Q${period.quarter}`;

  return (
    <div>
      <PageHeader eyebrow="Обзор" title="Дашборд" subtitle={subtitle} />

      <Space wrap style={{ marginBottom: 24 }}>
        <QuarterPicker value={period} onChange={setPeriod} />
        <FactFilterBar />
        <ExportButtons
          onXlsx={() => downloadAnalyticsXlsx(undefined, undefined, teamParams)}
          onPdf={() => downloadAnalyticsPdf(undefined, undefined, teamParams)}
        />
        <Button
          icon={<SyncOutlined spin={syncFull.isPending} />}
          loading={syncFull.isPending}
          onClick={() =>
            syncFull.mutate(undefined, {
              onSuccess: (res) => notification.success({ title: 'Синхронизация завершена', description: res.message }),
              onError: (e) => notification.error({ title: 'Ошибка синхронизации', description: e.message }),
            })
          }
        >
          Синхронизация
        </Button>
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

      <Collapse
        items={[{
          key: 'sync',
          label: 'Статус синхронизации',
          children: syncLoading ? <Spin /> : (
            <Table<SyncStatusResponse>
              dataSource={syncStatus}
              rowKey="entity"
              pagination={false}
              size="small"
              scroll={{ x: true }}
              columns={[
                { title: 'Сущность', dataIndex: 'entity' },
                { title: 'Последняя синхронизация', dataIndex: 'last_sync', render: (v: string | null) => formatDate(v) },
                { title: 'Статус', dataIndex: 'last_error', render: (v: string | null) => v ? <Tag color="red">Ошибка</Tag> : <Tag color="green">OK</Tag> },
              ]}
            />
          ),
        }]}
      />
    </div>
  );
}
