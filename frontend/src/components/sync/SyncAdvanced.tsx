import { useRef, useState, useMemo } from 'react';
import {
  Button, Card, Checkbox, DatePicker, Popconfirm, Progress, Space, Typography, App,
} from 'antd';
import {
  ReloadOutlined, CloseOutlined, ExclamationCircleOutlined,
} from '@ant-design/icons';
import dayjs, { type Dayjs } from 'dayjs';
import {
  useReloadWorklogs, useUpdateWorklogs,
} from '../../hooks/useSync';
import { useGenericSetting, useSaveGenericSetting } from '../../hooks/useSettings';
import type { WorklogReloadProgress, WorklogUpdateProgress } from '../../api/sync';
import { DARK_THEME } from '../../utils/constants';

const { Text } = Typography;

/** Ворклог breakglass: backfill с произвольной даты + полная перезагрузка
 *  (единственный способ вычистить worklog, удалённые в Jira). */
export default function SyncAdvanced() {
  const { notification } = App.useApp();

  // ─── Worklogs date ───────────────────────────────────────
  const reloadSince = useGenericSetting('worklog_reload_since_date');
  const saveReloadSince = useSaveGenericSetting();
  const storedSinceDate = useMemo(
    () => dayjs(reloadSince.data?.value || '2026-01-01'),
    [reloadSince.data?.value],
  );
  const [selectedSinceDate, setSelectedSinceDate] = useState<Dayjs | null>(null);
  const sinceDate = selectedSinceDate ?? storedSinceDate;

  // ─── Worklogs team filter ────────────────────────────────
  const storedCategoryTeams = useGenericSetting('ui_teams_categories');
  const categoryTeams = useMemo(
    () => (storedCategoryTeams.data?.value ?? '').split(',').filter(Boolean),
    [storedCategoryTeams.data],
  );
  const [includeTeams, setIncludeTeams] = useState(false);

  // ─── Reload worklogs ─────────────────────────────────────
  const reload = useReloadWorklogs();
  const reloadAbortRef = useRef<AbortController | null>(null);
  const [reloadProgress, setReloadProgress] = useState<WorklogReloadProgress | null>(null);

  const handleReload = () => {
    const iso = sinceDate.format('YYYY-MM-DD');
    const ctl = new AbortController();
    reloadAbortRef.current = ctl;
    setReloadProgress(null);
    reload.mutate(
      { req: { since: iso }, onProgress: (e) => setReloadProgress(e), signal: ctl.signal },
      {
        onSuccess: (stats) => {
          notification.success({
            title: "Worklog'и перезагружены",
            description: `Удалено: ${stats.deleted}, issues: ${stats.issues_scanned}, вставлено: ${stats.worklogs_inserted}`,
          });
          saveReloadSince.mutate({ key: 'worklog_reload_since_date', value: iso });
        },
        onError: (e) => {
          if (e.name === 'AbortError') return;
          notification.error({ title: 'Ошибка', description: e.message });
        },
        onSettled: () => {
          reloadAbortRef.current = null;
          setReloadProgress(null);
        },
      },
    );
  };
  const cancelReload = () => reloadAbortRef.current?.abort();

  // ─── Update worklogs ─────────────────────────────────────
  const update = useUpdateWorklogs();
  const updateAbortRef = useRef<AbortController | null>(null);
  const [updateProgress, setUpdateProgress] = useState<WorklogUpdateProgress | null>(null);

  const handleUpdate = () => {
    const iso = sinceDate.format('YYYY-MM-DD');
    const ctl = new AbortController();
    updateAbortRef.current = ctl;
    setUpdateProgress(null);
    update.mutate(
      {
        req: {
          since: iso,
          teams: includeTeams && categoryTeams.length ? categoryTeams : undefined,
        },
        onProgress: (e) => setUpdateProgress(e),
        signal: ctl.signal,
      },
      {
        onSuccess: (stats) => {
          notification.success({
            title: 'Ворклоги обновлены',
            description:
              `A: issues ${stats.bucket_a_issues_scanned}, worklog ${stats.bucket_a_worklogs_upserted}. ` +
              `B: issues ${stats.bucket_b_issues_scanned}, worklog ${stats.bucket_b_worklogs_upserted}, ` +
              `новых вне scope ${stats.bucket_b_out_of_scope_created}`,
          });
          saveReloadSince.mutate({ key: 'worklog_reload_since_date', value: iso });
        },
        onError: (e) => {
          if (e.name === 'AbortError') return;
          notification.error({ title: 'Ошибка обновления', description: e.message });
        },
        onSettled: () => {
          updateAbortRef.current = null;
          setUpdateProgress(null);
        },
      },
    );
  };
  const cancelUpdate = () => updateAbortRef.current?.abort();

  const worklogsInProgress = reload.isPending || update.isPending;

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%' }}>
      <Text type="secondary" style={{ fontSize: 12 }}>
        Ручной backfill ворклогов с произвольной даты и полная перезагрузка
        (единственный способ подчистить worklog, удалённые в&nbsp;Jira). В&nbsp;повседневке
        используйте «Синхронизация».
      </Text>
      <Card title="Ворклоги" size="small">
        <Space orientation="vertical" style={{ width: '100%' }}>
          <Space wrap>
            <DatePicker
              value={sinceDate}
              onChange={(d) => d && setSelectedSinceDate(d)}
              format="DD.MM.YYYY"
              allowClear={false}
              disabled={worklogsInProgress}
            />
            {update.isPending ? (
              <Button danger icon={<CloseOutlined />} onClick={cancelUpdate}>
                Прервать обновление ворклогов
              </Button>
            ) : (
              <Button
                type="primary"
                icon={<ReloadOutlined />}
                onClick={handleUpdate}
                disabled={reload.isPending}
              >
                Обновить ворклоги с даты
              </Button>
            )}
            <Checkbox
              checked={includeTeams}
              disabled={worklogsInProgress || categoryTeams.length === 0}
              onChange={(e) => setIncludeTeams(e.target.checked)}
            >
              Включить выбранные команды ({categoryTeams.length})
            </Checkbox>
            {reload.isPending ? (
              <Button danger icon={<CloseOutlined />} onClick={cancelReload}>
                Прервать перезагрузку
              </Button>
            ) : (
              <Popconfirm
                title="Полная перезагрузка ворклогов"
                description={
                  <div style={{ maxWidth: 340 }}>
                    <b>Удалит</b> все worklog с started ≥ {sinceDate.format('DD.MM.YYYY')} и
                    перечитает из Jira. В повседневке — «Обновить ворклоги с даты».
                  </div>
                }
                icon={<ExclamationCircleOutlined style={{ color: '#ff4d4f' }} />}
                okText="Перезагрузить"
                cancelText="Отмена"
                okButtonProps={{ danger: true }}
                onConfirm={handleReload}
                disabled={update.isPending}
              >
                <Button danger icon={<ReloadOutlined />} disabled={update.isPending}>
                  Полная перезагрузка (удалить и перечитать)
                </Button>
              </Popconfirm>
            )}
          </Space>

          {worklogsInProgress && (
            <Space orientation="vertical" size={2} style={{ width: '100%', maxWidth: 640 }}>
              <Progress
                percent={99.9}
                status="active"
                showInfo={false}
                strokeColor={DARK_THEME.cyanPrimary}
              />
              <Text type="secondary" style={{ fontSize: 12 }}>
                {update.isPending ? (
                  updateProgress
                    ? `A: issues ${updateProgress.bucket_a_issues_scanned} · worklog ${updateProgress.bucket_a_worklogs_upserted} · B: issues ${updateProgress.bucket_b_issues_scanned} · worklog ${updateProgress.bucket_b_worklogs_upserted}${updateProgress.current_key ? ` · ${updateProgress.current_key}` : ''}`
                    : 'Подготовка…'
                ) : (
                  reloadProgress
                    ? `Удалено: ${reloadProgress.deleted} · Обработано: ${reloadProgress.issues_scanned} · Вставлено: ${reloadProgress.worklogs_inserted}${reloadProgress.current_key ? ` · ${reloadProgress.current_key}` : ''}`
                    : 'Подготовка…'
                )}
              </Text>
            </Space>
          )}
        </Space>
      </Card>

    </Space>
  );
}
