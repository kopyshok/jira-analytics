import { useState } from 'react';
import { Link } from 'react-router';
import { Alert, App, Button, Checkbox, Descriptions, Space, Tag, Typography } from 'antd';
import type { MigrationOverview } from '../../../api/jiraMigration';
import { useApplyMigration, usePostCheck, useRestartFullSync } from '../../../hooks/useJiraMigration';
import {
  SYNC_STATUS_COLOR, SYNC_STATUS_LABEL, applySummaryItems, fmtDateTime, formatHours, offerFullSyncRestart,
  totalHoursLeaving,
} from '../../../utils/jiraMigration';

const { Paragraph, Text } = Typography;

function AppliedView({ overview }: { overview: MigrationOverview }) {
  const { notification } = App.useApp();
  const restartSync = useRestartFullSync();
  const postCheck = usePostCheck();

  const jobRunning = overview.job.state === 'running';
  const sync = overview.sync_run;
  const checkBlocked = jobRunning || sync?.status === 'running';
  const summary = overview.apply_summary ? applySummaryItems(overview.apply_summary) : [];
  const check = overview.post_check;
  const flagged = check ? check.rows.filter((r) => r.flagged).length : 0;

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%', maxWidth: 900 }}>
      <Alert
        type="success"
        showIcon
        title="Переезд применён"
        description={`База переведена на новую Jira ${fmtDateTime(overview.applied_at)}. Синхронизация снова работает.`}
      />
      {summary.length > 0 && (
        <Descriptions bordered size="small" column={1} title="Что изменилось">
          {summary.map((item) => (
            <Descriptions.Item key={item.key} label={item.label}>
              {item.value.toLocaleString('ru-RU')}
              {item.detail && <div><Text type="secondary" style={{ fontSize: 12 }}>{item.detail}</Text></div>}
            </Descriptions.Item>
          ))}
        </Descriptions>
      )}
      <Descriptions bordered size="small" column={1} title="Полная синхронизация после переезда">
        <Descriptions.Item label="Состояние">
          <Space wrap>
            {sync
              ? <Tag color={SYNC_STATUS_COLOR[sync.status] ?? 'default'}>{SYNC_STATUS_LABEL[sync.status] ?? sync.status}</Tag>
              : <Text type="secondary">{jobRunning ? 'Запускается' : 'Не запускалась'}</Text>}
            <Link to="/sync">История синхронизаций</Link>
          </Space>
        </Descriptions.Item>
        {sync?.started_at && <Descriptions.Item label="Начата">{fmtDateTime(sync.started_at)}</Descriptions.Item>}
        {sync?.finished_at && <Descriptions.Item label="Закончена">{fmtDateTime(sync.finished_at)}</Descriptions.Item>}
        {sync?.error && <Descriptions.Item label="Ошибка">{sync.error}</Descriptions.Item>}
      </Descriptions>
      {offerFullSyncRestart(overview.job, sync) && (
        <>
          <Paragraph type="secondary" style={{ marginBottom: 0 }}>
            Полная синхронизация после переезда загружает задачи и все списания с самой ранней
            даты, что была в сервисе. Она не завершилась успешно — запустите её заново отсюда:
            обычный «полный» режим на странице синхронизации грузит списания только за последние
            90 дней.
          </Paragraph>
          <div>
            <Button
              loading={restartSync.isPending}
              onClick={() =>
                restartSync.mutate(undefined, {
                  onSuccess: () => notification.info({ title: 'Полная синхронизация запущена' }),
                  onError: (e) => notification.error({ title: 'Не удалось запустить', description: e.message }),
                })
              }
            >
              Запустить полную синхронизацию заново
            </Button>
          </div>
        </>
      )}
      <Typography.Title level={5} style={{ margin: 0 }}>Сверка после переезда</Typography.Title>
      <Paragraph type="secondary" style={{ marginBottom: 0 }}>
        Сравнивает часы в базе сейчас с часами новой Jira на момент пробного прогона — по
        командам и месяцам. Запускайте после окончания полной синхронизации.
      </Paragraph>
      {check && (
        <Paragraph style={{ marginBottom: 0 }}>
          Сверка от {fmtDateTime(check.checked_at)}: списаний в базе —{' '}
          {check.db_worklogs.toLocaleString('ru-RU')}, в новой Jira на момент прогона —{' '}
          {check.dc_worklogs.toLocaleString('ru-RU')}; месяцев с расхождением больше 1 % — {flagged}.
          Таблица — на вкладке «Часы».
        </Paragraph>
      )}
      <div>
        <Button
          type="primary"
          disabled={checkBlocked}
          loading={postCheck.isPending}
          onClick={() =>
            postCheck.mutate(undefined, {
              onSuccess: () =>
                notification.success({ title: 'Сверка готова', description: 'Таблица — на вкладке «Часы».' }),
              onError: (e) => notification.error({ title: 'Сверка не удалась', description: e.message }),
            })
          }
        >
          Сверить после переезда
        </Button>
        {checkBlocked && (
          <Text type="secondary" style={{ marginLeft: 12 }}>Доступна после окончания полной синхронизации</Text>
        )}
      </div>
    </Space>
  );
}

function PendingView({ overview }: { overview: MigrationOverview }) {
  const { modal, notification } = App.useApp();
  const [backup, setBackup] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const apply = useApplyMigration();

  const running = overview.job.state === 'running';
  const blocked = overview.blockers.length > 0;
  const choicesDropped = overview.report?.choices_dropped ?? 0;
  const issues = overview.report?.issues;
  const toDelete = issues?.to_delete_total ?? 0;
  const deleteHours = issues?.to_delete_hours ?? 0;
  const leavingHours = totalHoursLeaving(overview.report?.people ?? []);

  const confirm = () => {
    setConfirming(true);
    modal.confirm({
      title: 'Применить переезд?',
      content: (
        <ul style={{ margin: 0, paddingLeft: 20 }}>
          <li>Отменить можно только восстановлением копии базы.</li>
          {toDelete > 0 && (
            <li>
              Задач будет удалено: {toDelete.toLocaleString('ru-RU')}
              {deleteHours > 0 && `; списания по ним — ${formatHours(deleteHours)} ч — пропадут из сервиса`}.
            </li>
          )}
          {leavingHours > 0 && (
            <li>
              У сотрудников без привязки уйдёт {formatHours(leavingHours)} ч по перенесённым задачам:
              полная синхронизация привяжет эти часы к новым карточкам без команды.
            </li>
          )}
          {choicesDropped > 0 && (
            <li>Задач, у которых сбросится выбор оценки: {choicesDropped.toLocaleString('ru-RU')}.</li>
          )}
          <li>
            Списания задач, перенесённых на новую Jira, вернутся полной синхронизацией — она запустится
            сама и идёт долго. Комментарии этих задач удаляются: после переезда сервис их не загружает.
          </li>
        </ul>
      ),
      okText: 'Применить',
      okButtonProps: { danger: true },
      cancelText: 'Отмена',
      onOk: () =>
        apply.mutate(backup, {
          onSuccess: () => notification.info({ title: 'Применение запущено', description: 'Ход обновляется сам.' }),
          onError: (e) => notification.error({ title: 'Не удалось применить', description: e.message }),
        }),
      afterClose: () => setConfirming(false),
    });
  };

  return (
    <Space orientation="vertical" size="middle" style={{ width: '100%', maxWidth: 900 }}>
      {blocked ? (
        <Alert
          type="warning"
          showIcon
          title="Применить пока нельзя"
          description={
            <ul style={{ margin: 0, paddingLeft: 20 }}>
              {overview.blockers.map((b) => <li key={b}>{b}</li>)}
            </ul>
          }
        />
      ) : (
        <Alert type="success" showIcon title="Отчёт готов к применению" />
      )}
      {choicesDropped > 0 && (
        <Alert
          type="warning"
          showIcon
          title={`Задач, у которых сбросится выбор оценки: ${choicesDropped.toLocaleString('ru-RU')}`}
          description="В споре оценок у этих задач выбрано поле, отмеченное на вкладке «Поля» как «Не использовать». После применения выбор сбросится — спор оценки придётся решить заново."
        />
      )}
      <Paragraph style={{ marginBottom: 0 }}>
        Перед применением сисадмин делает свежую копию базы — на сервере, в папке сервиса:
      </Paragraph>
      <Text code copyable>{overview.backup_command}</Text>
      <Paragraph type="secondary" style={{ marginBottom: 0 }}>
        Если после применения что-то пойдёт не так, базу возвращают из этой копии.
      </Paragraph>
      <Checkbox checked={backup} disabled={running} onChange={(e) => setBackup(e.target.checked)}>
        Свежая копия базы сделана
      </Checkbox>
      <Paragraph style={{ marginBottom: 0 }}>
        «Применить» за один шаг переводит задачи, проекты, сотрудников и настройки полей на новую
        Jira и удаляет задачи по решениям. У задач, перенесённых на новую Jira, удаляются списания
        и комментарии: списания вернутся полной синхронизацией, комментарии после переезда сервис
        не загружает. У задач, оставшихся со старыми номерами (оставленные по решению и задачи
        проектов, которых нет в новой Jira), списания и комментарии сохраняются. Затем сама
        запускается полная синхронизация. Если на любом шаге случится ошибка, база не изменится.
      </Paragraph>
      <div>
        <Button type="primary" danger disabled={!backup || blocked || running || confirming} loading={apply.isPending} onClick={confirm}>
          Применить
        </Button>
      </div>
    </Space>
  );
}

export default function ApplySection({ overview }: { overview: MigrationOverview }) {
  const applied = overview.migration_state === 'done' || overview.applied_at !== null;
  return applied ? <AppliedView overview={overview} /> : <PendingView overview={overview} />;
}
