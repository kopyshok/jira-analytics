import { useEffect, useState } from 'react';
import { App, Card, Select, Space, Switch, Typography } from 'antd';
import { useQueryClient } from '@tanstack/react-query';
import { getGenericSetting, saveGenericSetting } from '../../api/settings';
import { OPO_CUTOFF_KEY } from '../../hooks/useOpoCutoff';

const KEY = 'planning_multi_team_by_epics';

const CUTOFF_OPTIONS = (() => {
  const nowYear = new Date().getFullYear();
  const out: { value: string; label: string }[] = [];
  for (let y = nowYear - 1; y <= nowYear + 3; y += 1) {
    for (let q = 1; q <= 4; q += 1) out.push({ value: `${y}Q${q}`, label: `${q} кв. ${y}` });
  }
  return out;
})();

export default function PlanningSettingsTab() {
  const { notification } = App.useApp();
  const qc = useQueryClient();
  const [enabled, setEnabled] = useState(true);
  const [loading, setLoading] = useState(true);
  const [cutoff, setCutoff] = useState<string | undefined>(undefined);

  useEffect(() => {
    getGenericSetting(KEY)
      .then((r) => setEnabled(r.value === null || r.value.toLowerCase() !== 'false'))
      .finally(() => setLoading(false));
    getGenericSetting(OPO_CUTOFF_KEY).then((r) => setCutoff(r.value || undefined));
  }, []);

  const saveCutoff = async (next?: string) => {
    const prev = cutoff;
    setCutoff(next);
    try {
      await saveGenericSetting(OPO_CUTOFF_KEY, next ?? '');
      void qc.invalidateQueries({ queryKey: [OPO_CUTOFF_KEY] });
      void qc.invalidateQueries({ queryKey: ['backlog'] });
      void qc.invalidateQueries({ queryKey: ['planning'] });
      notification.success({ title: 'Сохранено' });
    } catch (e) {
      setCutoff(prev);
      notification.error({ title: 'Ошибка', description: (e as Error).message });
    }
  };

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

        <Space align="start" size={12}>
          <Select
            allowClear
            placeholder="ОПЭ планируем всегда"
            style={{ width: 200 }}
            value={cutoff}
            options={CUTOFF_OPTIONS}
            onChange={(v) => saveCutoff(v || undefined)}
          />
          <Space orientation="vertical" size={2}>
            <Typography.Text strong>ОПЭ не планируем начиная с квартала</Typography.Text>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              С выбранного квартала этап ОПЭ пропадает из целевых задач, сценариев,
              ресурсного планирования и выгрузок. Часы ОПЭ не теряются: они уходят в Анализ
              и Разработку по доле, заданной у задачи. Кварталы до отсечки остаются как были.
            </Typography.Text>
          </Space>
        </Space>
      </Space>
    </Card>
  );
}
