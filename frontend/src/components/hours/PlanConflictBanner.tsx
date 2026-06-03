import { Alert, Button, Space, App } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getPlanConflicts, resolvePlanConflict } from '../../api/issues';

interface Props { issueId: string }

const ROLE_LABEL: Record<string, string> = {
  analyst: 'Аналитик', dev: 'Разработка', qa: 'Тестирование', opo: 'ОПЭ',
};

export default function PlanConflictBanner({ issueId }: Props) {
  const qc = useQueryClient();
  const { message } = App.useApp();
  const { data } = useQuery({
    queryKey: ['plan-conflicts', issueId],
    queryFn: () => getPlanConflicts(issueId),
    staleTime: 30_000,
  });
  const resolveMut = useMutation({
    mutationFn: ({ action, role }: { action: 'accept_jira' | 'ignore'; role: string }) =>
      resolvePlanConflict(issueId, action, role),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['plan-conflicts', issueId] });
      void qc.invalidateQueries({ queryKey: ['hours-breakdown'] });
      void qc.invalidateQueries({ queryKey: ['plan-history', issueId] });
      void qc.invalidateQueries({ queryKey: ['backlog'] });
    },
    onError: () => { void message.error('Не удалось разрешить конфликт'); },
  });
  if (!data || data.length === 0) return null;
  return (
    <div style={{ marginBottom: 12 }}>
      {data.map((c) => (
        <Alert
          key={c.audit_id}
          type="warning"
          showIcon
          message={`В Jira план изменили на ${c.value_jira ?? '—'}ч (${ROLE_LABEL[c.role] ?? c.role}). Сейчас активна ручная правка.`}
          action={
            <Space>
              <Button size="small" onClick={() => resolveMut.mutate({ action: 'accept_jira', role: c.role })}>
                Принять Jira
              </Button>
              <Button size="small" onClick={() => resolveMut.mutate({ action: 'ignore', role: c.role })}>
                Игнорировать
              </Button>
            </Space>
          }
          style={{ marginBottom: 6 }}
        />
      ))}
    </div>
  );
}
