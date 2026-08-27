import { useEffect, useState } from 'react';
import { App, Card, Space, Switch, Typography } from 'antd';
import { useQueryClient } from '@tanstack/react-query';
import { getGenericSetting, saveGenericSetting } from '../../api/settings';

const KEY = 'planning_multi_team_by_epics';

export default function PlanningSettingsTab() {
  const { notification } = App.useApp();
  const qc = useQueryClient();
  const [enabled, setEnabled] = useState(true);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getGenericSetting(KEY)
      .then((r) => setEnabled(r.value === null || r.value.toLowerCase() !== 'false'))
      .finally(() => setLoading(false));
  }, []);

  const toggle = async (next: boolean) => {
    setEnabled(next);
    try {
      await saveGenericSetting(KEY, next ? 'true' : 'false');
      void qc.invalidateQueries({ queryKey: ['backlog'] });
      void qc.invalidateQueries({ queryKey: ['planning'] });
      notification.success({ title: 'Сохранено' });
    } catch (e) {
      setEnabled(!next);
      notification.error({ title: 'Ошибка', description: (e as Error).message });
    }
  };

  return (
    <Card title="Планирование">
      <Space orientation="vertical" size={12} style={{ width: '100%' }}>
        <Space align="start" size={12}>
          <Switch checked={enabled} loading={loading} onChange={toggle} />
          <Space orientation="vertical" size={2}>
            <Typography.Text strong>
              Мультикомандные RFA планировать только по Эпикам
            </Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              Если над задачей работает несколько команд, взять её в сценарий целиком нельзя —
              каждая команда планирует свой Эпик. Переключатель режима у такой RFA заблокирован.
            </Typography.Text>
          </Space>
        </Space>
        <Typography.Text type="secondary" style={{ fontSize: 12 }}>
          Мультикомандной считается задача, у которой участвующих команд больше одной либо
          единственная участвующая команда не совпадает с продуктовой. Список участников берётся
          из поля Jira, указанного в разделе «Поля Jira».
        </Typography.Text>
      </Space>
    </Card>
  );
}
