import { useEffect, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Alert, App, Badge, Button, Empty, Space, Spin, Tabs, Typography } from 'antd';
import type { TabsProps } from 'antd';
import { PlayCircleOutlined } from '@ant-design/icons';
import type { JobKind, MigrationJob } from '../../../api/jiraMigration';
import { useMigrationOverview, useStartDryRun } from '../../../hooks/useJiraMigration';
import { JOB_KIND_LABEL, counterLines, fmtDateTime } from '../../../utils/jiraMigration';
import ApplySection from './ApplySection';
import FieldsSection from './FieldsSection';
import HoursSection from './HoursSection';
import IssuesSection from './IssuesSection';
import PeopleSection from './PeopleSection';
import ProbeSection from './ProbeSection';

const { Paragraph, Text } = Typography;

const JOB_FAILED_TITLE: Record<JobKind, string> = {
  dry_run: 'Пробный прогон не удался',
  apply: 'Применение не удалось',
  full_sync: 'Полная синхронизация после переезда не удалась',
};

function JobProgress({ job }: { job: MigrationJob }) {
  const counters = counterLines(job.counters);
  return (
    <Alert
      type="info"
      showIcon
      icon={<Spin size="small" />}
      title={`${job.kind ? JOB_KIND_LABEL[job.kind] : 'Операция'} — идёт`}
      description={
        <>
          {job.step && <div>Этап: {job.step}</div>}
          {counters.length > 0 && <div>{counters.join(' · ')}</div>}
          {job.started_at && <div>Начато: {fmtDateTime(job.started_at)}</div>}
          <div>Страницу можно закрыть — работа продолжится.</div>
        </>
      }
    />
  );
}

function tabLabel(text: string, count: number) {
  return (
    <Badge count={count} size="small" offset={[10, 0]}>
      {text}
    </Badge>
  );
}

export default function JiraMigrationTab() {
  const { notification } = App.useApp();
  const qc = useQueryClient();
  const overview = useMigrationOverview();
  const startDryRun = useStartDryRun();
  const [tab, setTab] = useState<string | null>(null);
  const data = overview.data;
  const migrationState = data?.migration_state;

  // Переезд завершён — плашка «синхронизация остановлена» по всему сервису должна исчезнуть.
  useEffect(() => {
    if (migrationState === 'done') {
      qc.invalidateQueries({ queryKey: ['ui-config', 'jira-migration-state'] });
    }
  }, [migrationState, qc]);

  if (overview.isLoading) return <Spin />;
  if (!data) {
    return (
      <Alert
        type="error"
        showIcon
        title="Не удалось загрузить состояние переезда"
        description={overview.error?.message}
      />
    );
  }

  // Свежая установка: данных старой Jira в базе не было, переезд не понадобился.
  if (data.migration_state === 'done' && !data.applied_at) {
    return (
      <Alert
        type="success"
        showIcon
        title="Переезд не требуется"
        description="В этой базе нет данных старой Jira — синхронизация работает как обычно."
      />
    );
  }

  const report = data.report;
  const job = data.job;
  const running = job.state === 'running';
  const building = report?.status === 'running';
  const busy = running || building;
  const applied = data.migration_state === 'done' || data.applied_at !== null;
  const ready = report?.status === 'done';
  const stale = (report?.age_hours ?? 0) > 24;
  const unresolved = data.unresolved;

  const items: NonNullable<TabsProps['items']> = [];
  if (report) items.push({ key: 'probe', label: 'Проверка Jira', children: <ProbeSection items={report.probe} /> });
  // Поля, задачи и сотрудники с решениями приходят только до применения и не во время него.
  if (report?.fields) {
    items.push({
      key: 'fields',
      label: tabLabel('Поля', unresolved.fields),
      children: <FieldsSection rows={report.fields} dcFields={report.dc_fields ?? []} readOnly={busy} />,
    });
  }
  if (report?.issues) {
    items.push({
      key: 'issues',
      label: tabLabel('Задачи', unresolved.issues),
      children: <IssuesSection summary={report.issues} readOnly={busy} />,
    });
  }
  if (report?.people) {
    items.push({
      key: 'people',
      label: tabLabel('Сотрудники', unresolved.people),
      children: <PeopleSection rows={report.people} readOnly={busy} />,
    });
  }
  if (report?.hours) {
    items.push({
      key: 'hours',
      label: 'Часы',
      children: (
        <HoursSection
          hours={report.hours}
          offsetHours={report.offset_hours ?? null}
          offsetMatches={report.offset_matches ?? 0}
          offsetSample={report.offset_sample ?? 0}
          offsetUnexpected={report.offset_unexpected}
          postCheck={data.post_check}
        />
      ),
    });
  }
  items.push({
    key: 'apply',
    label: applied ? 'Итог переезда' : 'Применить',
    children: <ApplySection overview={data} />,
  });

  let firstOpen = 'apply';
  if (!applied && unresolved.fields) firstOpen = 'fields';
  else if (!applied && unresolved.issues) firstOpen = 'issues';
  else if (!applied && unresolved.people) firstOpen = 'people';
  const showTabs = applied || ready;
  // Вкладка по умолчанию выбирается один раз — при первом показе отчёта; обновления
  // данных (решения, опрос хода) её не переключают. Пропавшая вкладка (после
  // применения) — показывается вкладка по умолчанию.
  if (tab === null && showTabs) setTab(firstOpen);
  const activeTab = tab !== null && items.some((i) => i.key === tab) ? tab : firstOpen;

  return (
    <Space orientation="vertical" size="large" style={{ width: '100%' }}>
      <Alert
        type="info"
        showIcon
        title="Переезд на новую Jira"
        description={
          <>
            <Paragraph style={{ marginBottom: 8 }}>
              Пробный прогон читает новую Jira и сравнивает её с базой сервиса: поля, задачи,
              сотрудников и часы. База при этом не меняется — сохраняется только отчёт.
            </Paragraph>
            <Paragraph style={{ marginBottom: 0 }}>
              Когда в отчёте не останется нерешённых пунктов и сисадмин сделает копию базы,
              «Применить» переведёт базу на новую Jira и запустит полную синхронизацию.
            </Paragraph>
          </>
        }
      />
      {!applied && (
        <Space wrap align="center">
          <Button
            type="primary"
            icon={<PlayCircleOutlined />}
            disabled={busy}
            loading={startDryRun.isPending}
            onClick={() =>
              startDryRun.mutate(undefined, {
                onError: (e) =>
                  notification.error({ title: 'Не удалось запустить пробный прогон', description: e.message }),
              })
            }
          >
            {report ? 'Запустить пробный прогон заново' : 'Запустить пробный прогон'}
          </Button>
          {report?.finished_at && (
            <Text type={stale ? 'warning' : 'secondary'}>
              Последний прогон: {fmtDateTime(report.finished_at)}
              {stale ? ' — старше суток, перед применением запустите заново' : ''}
            </Text>
          )}
        </Space>
      )}
      {running && <JobProgress job={job} />}
      {building && !running && (
        <Alert
          type="info"
          showIcon
          title="Идёт пробный прогон"
          description="Отчёт появится здесь, когда прогон закончится — обновите страницу позже."
        />
      )}
      {job.state === 'error' && job.error && (
        <Alert
          type="error"
          showIcon
          title={job.kind ? JOB_FAILED_TITLE[job.kind] : 'Операция не удалась'}
          description={job.error}
        />
      )}
      {report?.status === 'failed' && report.error && !(job.state === 'error' && job.kind === 'dry_run') && (
        <Alert type="error" showIcon title="Последний пробный прогон завершился с ошибкой" description={report.error} />
      )}
      {!report && !busy && !applied && <Empty description="Пробный прогон ещё не запускался" />}
      {report && !showTabs && report.probe.length > 0 && <ProbeSection items={report.probe} />}
      {showTabs && <Tabs activeKey={activeTab} onChange={setTab} items={items} />}
    </Space>
  );
}
