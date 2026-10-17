import { useState } from 'react';
import { App, Button, Card, Checkbox, Space, Spin, Typography } from 'antd';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { getHiddenSections, putHiddenSections } from '../../api/uiConfig';

interface SectionDef {
  key: string;
  label: string;
  group: string;
}

// Должен совпадать со списком в меню (см. aurora/shell/AuroraSidebar.tsx).
const SECTIONS: SectionDef[] = [
  { group: 'Обзор', key: '/', label: 'Дашборд' },
  { group: 'Обзор', key: '/projects', label: 'Проекты' },
  { group: 'Обзор', key: '/analytics', label: 'Аналитика' },
  { group: 'Обзор', key: '/analytics/work-type-report', label: 'Тематический отчёт' },
  { group: 'Обзор', key: '/executive', label: 'Сводка для руководителя' },
  { group: 'Обзор', key: '/kpi', label: 'KPI' },
  { group: 'Обзор', key: '/team-desk', label: 'Стол тимлида' },
  { group: 'Планирование', key: '/capacity', label: 'Ресурсы' },
  { group: 'Планирование', key: '/backlog', label: 'Целевые задачи' },
  { group: 'Планирование', key: '/planning', label: 'Сценарии' },
  { group: 'Планирование', key: '/resource-planning', label: 'Ресурс. планир.' },
  { group: 'Данные', key: '/sync', label: 'Синхронизация' },
  { group: 'Данные', key: '/categories', label: 'Категории задач' },
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
    <Space orientation="vertical" size="large" style={{ width: '100%', maxWidth: 720 }}>
      <Typography.Paragraph type="secondary">
        Отметьте разделы, которые нужно скрыть из бокового меню. Изменения применяются для всех пользователей после перезагрузки страницы.
      </Typography.Paragraph>
      {groups.map((g) => (
        // Регистр подписи — стилем: в Aurora заглавными, как раньше; скины показывают обычным регистром.
        <Card key={g} size="small" title={<span style={{ textTransform: 'uppercase' }}>{g}</span>}>
          <Space orientation="vertical">
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
