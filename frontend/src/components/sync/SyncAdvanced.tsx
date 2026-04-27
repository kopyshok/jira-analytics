import { useRef, useState, useMemo } from 'react';
import {
  Button, Card, Checkbox, DatePicker, Popconfirm, Progress, Space, Typography, App,
} from 'antd';
import {
  ReloadOutlined, CloseOutlined, ExclamationCircleOutlined, TeamOutlined,
} from '@ant-design/icons';
import dayjs, { type Dayjs } from 'dayjs';
import {
  useReloadWorklogs, useUpdateWorklogs, useRecalculateMapping,
  useSyncMutation,
} from '../../hooks/useSync';
import { useAutoDetectTeams } from '../../hooks/useCapacity';
import { useGenericSetting, useSaveGenericSetting } from '../../hooks/useSettings';
import type { WorklogReloadProgress, WorklogUpdateProgress } from '../../api/sync';
import { useScopeProjects } from '../../hooks/useScope';
import { DARK_THEME } from '../../utils/constants';

const { Text } = Typography;

/** Продвинутые операции синхронизации — ручные команды для PM. */
export default function SyncAdvanced() {
  const { notification } = App.useApp();

  // ─── Scope ───────────────────────────────────────────────
  const scopeProjects = useScopeProjects();
  const scopeKeys = (scopeProjects.data ?? []).map((p) => p.jira_project_key);

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
            message: "Worklog'и перезагружены",
            description: `Удалено: ${stats.deleted}, issues: ${stats.issues_scanned}, вставлено: ${stats.worklogs_inserted}`,
          });
          saveReloadSince.mutate({ key: 'worklog_reload_since_date', value: iso });
        },
        onError: (e) => {
          if (e.name === 'AbortError') return;
          notification.error({ message: 'Ошибка', description: e.message });
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
            message: 'Ворклоги обновлены',
            description:
              `A: issues ${stats.bucket_a_issues_scanned}, worklog ${stats.bucket_a_worklogs_upserted}. ` +
              `B: issues ${stats.bucket_b_issues_scanned}, worklog ${stats.bucket_b_worklogs_upserted}, ` +
              `новых вне scope ${stats.bucket_b_out_of_scope_created}`,
          });
          saveReloadSince.mutate({ key: 'worklog_reload_since_date', value: iso });
        },
        onError: (e) => {
          if (e.name === 'AbortError') return;
          notification.error({ message: 'Ошибка обновления', description: e.message });
        },
        onSettled: () => {
          updateAbortRef.current = null;
          setUpdateProgress(null);
        },
      },
    );
  };
  const cancelUpdate = () => updateAbortRef.current?.abort();

  // ─── Full / incremental issue sync ───────────────────────
  const fullSyncMut = useSyncMutation('full');
  const incrementalSyncMut = useSyncMutation('full');
  const fullAbortRef = useRef<AbortController | null>(null);
  const incAbortRef = useRef<AbortController | null>(null);

  const handleFullSync = () => {
    const body = { project_keys: scopeKeys.length > 0 ? scopeKeys : undefined, incremental: false };
    const ctl = new AbortController();
    fullAbortRef.current = ctl;
    fullSyncMut.mutate({ body, signal: ctl.signal }, {
      onSuccess: (res) =>
        notification.success({ message: 'Полная синхронизация', description: res.message }),
      onError: (e) => {
        if (e.name === 'AbortError') return;
        notification.error({ message: 'Ошибка', description: e.message });
      },
      onSettled: () => { fullAbortRef.current = null; },
    });
  };
  const cancelFullSync = () => fullAbortRef.current?.abort();

  const handleIncrementalSync = () => {
    const body = { project_keys: scopeKeys.length > 0 ? scopeKeys : undefined, incremental: true };
    const ctl = new AbortController();
    incAbortRef.current = ctl;
    incrementalSyncMut.mutate({ body, signal: ctl.signal }, {
      onSuccess: (res) =>
        notification.success({ message: 'Обновление задач', description: res.message }),
      onError: (e) => {
        if (e.name === 'AbortError') return;
        notification.error({ message: 'Ошибка', description: e.message });
      },
      onSettled: () => { incAbortRef.current = null; },
    });
  };
  const cancelIncSync = () => incAbortRef.current?.abort();

  // ─── Recalculate mapping ─────────────────────────────────
  const recalculate = useRecalculateMapping();

  // ─── Auto-detect teams ───────────────────────────────────
  const autoDetect = useAutoDetectTeams();

  const worklogsInProgress = reload.isPending || update.isPending;

  return (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      {/* Синхронизация задач */}
      <Card title="Синхронизация задач (legacy)" size="small">
        <Space wrap>
          {incrementalSyncMut.isPending ? (
            <Button danger icon={<CloseOutlined />} onClick={cancelIncSync}>
              Прервать обновление
            </Button>
          ) : (
            <Button icon={<ReloadOutlined />} onClick={handleIncrementalSync}>
              Обновить задачи (incremental)
            </Button>
          )}
          {fullSyncMut.isPending ? (
            <Button danger icon={<CloseOutlined />} onClick={cancelFullSync}>
              Прервать полную синхронизацию
            </Button>
          ) : (
            <Popconfirm
              title="Полная синхронизация"
              description={
                <div style={{ maxWidth: 320 }}>
                  Перечитает все задачи из Jira заново (~115k+). В повседневке — «Обновить задачи».
                </div>
              }
              icon={<ExclamationCircleOutlined style={{ color: '#faad14' }} />}
              okText="Запустить"
              cancelText="Отмена"
              okButtonProps={{ danger: true }}
              onConfirm={handleFullSync}
            >
              <Button icon={<ReloadOutlined />}>Полная синхронизация задач</Button>
            </Popconfirm>
          )}
        </Space>
      </Card>

      {/* Ворклоги */}
      <Card title="Ворклоги" size="small">
        <Space direction="vertical" style={{ width: '100%' }}>
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
            <Space direction="vertical" size={2} style={{ width: '100%', maxWidth: 640 }}>
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

      {/* Прочее */}
      <Card title="Служебные операции" size="small">
        <Space wrap>
          <Button
            icon={<ReloadOutlined />}
            loading={recalculate.isPending}
            onClick={() =>
              recalculate.mutate(undefined, {
                onSuccess: (res) =>
                  notification.success({ message: 'Маппинг пересчитан', description: res.message }),
                onError: (e) =>
                  notification.error({ message: 'Ошибка маппинга', description: e.message }),
              })
            }
          >
            Пересчитать маппинг категорий
          </Button>
          <Button
            icon={<TeamOutlined />}
            loading={autoDetect.isPending}
            onClick={() =>
              autoDetect.mutate(undefined, {
                onSuccess: (res) =>
                  notification.success({
                    message: 'Команды определены',
                    description: `Назначено: ${res.assigned}, пропущено: ${res.skipped}`,
                  }),
                onError: (e) =>
                  notification.error({ message: 'Ошибка', description: e.message }),
              })
            }
          >
            Авто-определить команды сотрудников
          </Button>
        </Space>
      </Card>
    </Space>
  );
}
