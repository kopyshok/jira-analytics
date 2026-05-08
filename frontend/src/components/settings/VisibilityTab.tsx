import { useState } from 'react';
import { App, Button, Card, Checkbox, Space, Spin, Typography } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getHiddenSections, putHiddenSections } from '../../api/uiConfig';

interface SectionDef {
  key: string;
  label: string;
  group: string;
}

// Должен совпадать со списком в SideMenu (см. components/Layout/SideMenu.tsx).
const SECTIONS: SectionDef[] = [
  { group: 'ОБЗОР', key: '/', label: 'Дашборд' },
  { group: 'ОБЗОР', key: '/projects', label: 'Проекты' },
  { group: 'ОБЗОР', key: '/analytics', label: 'Аналитика' },
  { group: 'ОБЗОР', key: '/analytics/work-type-report', label: 'Тематический отчёт' },
  { group: 'ОБЗОР', key: '/executive', label: 'Сводка для руководителя' },
  { group: 'ПЛАНИРОВАНИЕ', key: '/capacity', label: 'Ресурсы' },
  { group: 'ПЛАНИРОВАНИЕ', key: '/backlog', label: 'Целевые задачи' },
  { group: 'ПЛАНИРОВАНИЕ', key: '/planning', label: 'Сценарии' },
  { group: 'ПЛАНИРОВАНИЕ', key: '/resource-planning', label: 'Ресурс. планир.' },
  { group: 'ПЛАНИРОВАНИЕ', key: '/resource-planning-v2', label: 'Планирование β' },
  { group: 'ПЛАНИРОВАНИЕ', key: '/resource-planning-v3', label: 'Планирование γ' },
  { group: 'ДАННЫЕ', key: '/sync', label: 'Синхронизация' },
  { group: 'ДАННЫЕ', key: '/categories', label: 'Категории задач' },
];

function Editor({ initialKeys }: { initialKeys: string[] }) {
  const { message } = App.useApp();
  const qc = useQueryClient();
  const [hidden, setHidden] = useState<Set<string>>(new Set(initialKeys));

  const mutation = useMutation({
    mutationFn: (keys: string[]) => putHiddenSections(keys),
    onSuccess: (resp) => {
      qc.setQueryData(['ui-config', 'hidden-sections'], resp);
      message.success('Сохранено. Перезагрузите страницу для применения.');
    },
    onError: (e: Error) => message.error(`Ошибка: ${e.message}`),
  });

  const toggle = (key: string) => {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const groups = Array.from(new Set(SECTIONS.map((s) => s.group)));

  return (
    <Space direction="vertical" size="large" style={{ width: '100%', maxWidth: 720 }}>
      <Typography.Paragraph type="secondary">
        Отметьте разделы, которые нужно скрыть из бокового меню. Изменения применяются для всех пользователей после перезагрузки страницы.
      </Typography.Paragraph>
      {groups.map((g) => (
        <Card key={g} size="small" title={g}>
          <Space direction="vertical">
            {SECTIONS.filter((s) => s.group === g).map((s) => (
              <Checkbox
                key={s.key}
                checked={hidden.has(s.key)}
                onChange={() => toggle(s.key)}
              >
                Скрыть «{s.label}»
              </Checkbox>
            ))}
          </Space>
        </Card>
      ))}
      <Button
        type="primary"
        loading={mutation.isPending}
        onClick={() => mutation.mutate(Array.from(hidden))}
      >
        Сохранить
      </Button>
    </Space>
  );
}

export default function VisibilityTab() {
  const { data, isLoading } = useQuery({
    queryKey: ['ui-config', 'hidden-sections'],
    queryFn: getHiddenSections,
  });

  if (isLoading || !data) return <Spin />;
  return <Editor key={data.keys.join(',')} initialKeys={data.keys} />;
}
