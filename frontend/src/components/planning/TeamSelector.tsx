import { Alert, Select, Spin } from 'antd';
import { useJiraTeams } from '../../hooks/useSync';

interface TeamSelectorProps {
  value: string | null;
  onChange: (team: string | null) => void;
  disabled?: boolean;
  placeholder?: string;
  style?: React.CSSProperties;
  status?: 'error' | 'warning';
}

export function TeamSelector({
  value,
  onChange,
  disabled,
  placeholder = 'Выберите команду',
  style,
  status,
}: TeamSelectorProps) {
  const { data: teams, isLoading, refetch } = useJiraTeams();

  if (isLoading) return <Spin size="small" />;

  if (teams && teams.length === 0) {
    return (
      <Alert
        type="warning"
        title="Список команд пуст. Загрузите проекты из Jira в разделе Синхронизация."
        showIcon
      />
    );
  }

  return (
    <Select
      value={value ?? undefined}
      onChange={(v) => onChange(v ?? null)}
      options={(teams ?? []).map((t) => ({ value: t, label: t }))}
      disabled={disabled}
      placeholder={placeholder}
      allowClear
      style={{ minWidth: 200, ...style }}
      status={status}
      showSearch
      onOpenChange={(open) => {
        if (open && !teams) refetch();
      }}
    />
  );
}
