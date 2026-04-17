import { useEffect, useState } from 'react';
import { Card, Form, Select, Button, Space, App } from 'antd';
import { SaveOutlined } from '@ant-design/icons';
import { useGenericSetting, useSaveGenericSetting } from '../hooks/useSettings';
import { useJiraFields } from '../hooks/useSync';

const FIELDS = [
  { key: 'jira_team_field_id', label: 'Поле продуктовой команды' },
  { key: 'jira_participating_teams_field_id', label: 'Поле участвующих команд' },
  { key: 'jira_goals_field_id', label: 'Поле целей' },
] as const;

export default function JiraFieldsCard() {
  const { message } = App.useApp();
  const save = useSaveGenericSetting();
  const jiraFields = useJiraFields();

  // Load each setting.
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const settings = FIELDS.map(f => ({ ...f, hook: useGenericSetting(f.key) }));
  const [values, setValues] = useState<Record<string, string>>({});
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (loaded) return;
    if (settings.every(s => s.hook.data !== undefined)) {
      const next: Record<string, string> = {};
      settings.forEach(s => { next[s.key] = s.hook.data?.value ?? ''; });
      setValues(next);
      setLoaded(true);
    }
  }, [loaded, settings]);

  const fieldOptions = (jiraFields.data ?? []).map(f => ({
    value: f.id,
    label: `${f.name} (${f.id})`,
  }));

  const handleSaveAll = () => {
    Promise.all(FIELDS.map(f =>
      save.mutateAsync({ key: f.key, value: values[f.key] ?? '' })
    )).then(() => message.success('Сохранено'))
      .catch(e => message.error(e.message));
  };

  return (
    <Card
      title="Кастомные поля Jira"
      size="small"
      extra={
        <Button
          size="small"
          icon={<SaveOutlined />}
          onClick={handleSaveAll}
          loading={save.isPending}
        >
          Сохранить
        </Button>
      }
    >
      <Form layout="vertical">
        <Space direction="vertical" style={{ width: '100%' }}>
          {FIELDS.map(f => (
            <Form.Item key={f.key} label={f.label} style={{ marginBottom: 0 }}>
              <Select
                value={values[f.key] || undefined}
                onChange={v => setValues(prev => ({ ...prev, [f.key]: v || '' }))}
                showSearch
                allowClear
                optionFilterProp="label"
                placeholder={`customfield_XXXXX`}
                options={fieldOptions}
                loading={jiraFields.isFetching}
                onDropdownVisibleChange={open => {
                  if (open && !jiraFields.data) jiraFields.refetch();
                }}
              />
            </Form.Item>
          ))}
        </Space>
      </Form>
    </Card>
  );
}
