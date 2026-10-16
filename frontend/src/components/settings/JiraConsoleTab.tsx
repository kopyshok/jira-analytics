import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Alert, App, Button, Checkbox, Input, Popconfirm, Segmented, Space, Table, Typography } from 'antd';
import { CopyOutlined, DeleteOutlined, DownloadOutlined, PlayCircleOutlined } from '@ant-design/icons';
import { consoleApi } from '../../api/console';
import type { ConsoleRun, ConsoleRunBrief, ConsoleTarget } from '../../api/console';

const { Text, Paragraph } = Typography;

const TITLES: Record<ConsoleTarget, string> = { jira: 'Jira', confluence: 'Confluence' };

// Готовые запросы: кнопка дописывает строки в конец поля, КЛЮЧ/НОМЕР заменить руками.
const PRESETS: Record<ConsoleTarget, { label: string; lines: string[] }[]> = {
  jira: [
    { label: 'Сведения о сервере', lines: ['/rest/api/2/serverInfo'] },
    { label: 'Все поля', lines: ['/rest/api/2/field'] },
    { label: 'Задача по ключу', lines: ['/rest/api/2/issue/КЛЮЧ'] },
    { label: 'Списания задачи', lines: ['/rest/api/2/issue/КЛЮЧ/worklog'] },
    { label: 'Поиск по условию', lines: ['/rest/api/2/search?jql=project = КЛЮЧ_ПРОЕКТА&maxResults=5'] },
    {
      label: 'Диагностический пакет',
      lines: [
        '# Диагностический пакет',
        '/rest/api/2/serverInfo',
        '/rest/api/2/myself',
        '/rest/api/2/field',
        '/rest/api/2/issuetype',
        '/rest/api/2/status',
        '/rest/api/2/priority',
        '/rest/api/2/resolution',
        '/rest/api/2/issueLinkType',
        '/rest/api/2/project',
      ],
    },
  ],
  confluence: [
    { label: 'Текущий пользователь', lines: ['/rest/api/user/current'] },
    { label: 'Пространства', lines: ['/rest/api/space?limit=50'] },
    { label: 'Страница по номеру', lines: ['/rest/api/content/НОМЕР?expand=version,space'] },
  ],
};

function fmt(dt: string): string {
  return new Date(dt).toLocaleString('ru-RU');
}

// Буфер обмена доступен только на https; иначе — через скрытое поле.
async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    return ok;
  }
}

function downloadRun(run: ConsoleRun) {
  const d = new Date(run.created_at);
  const p = (n: number) => String(n).padStart(2, '0');
  const name = `${run.target}-console-${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}.txt`;
  const url = URL.createObjectURL(new Blob([run.output_text], { type: 'text/plain;charset=utf-8' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export default function JiraConsoleTab() {
  const { notification } = App.useApp();
  const qc = useQueryClient();
  const [target, setTarget] = useState<ConsoleTarget>('jira');
  const [text, setText] = useState('');
  const [mask, setMask] = useState(true);
  const [current, setCurrent] = useState<ConsoleRun | null>(null);

  const history = useQuery({
    queryKey: ['admin', 'console-runs'],
    queryFn: () => consoleApi.list(),
  });

  const runMut = useMutation({
    mutationFn: () => consoleApi.run({ target, text, mask }),
    onSuccess: (run) => {
      setCurrent(run);
      qc.invalidateQueries({ queryKey: ['admin', 'console-runs'] });
    },
    onError: (e: Error) => notification.error({ title: 'Запуск не выполнен', description: e.message }),
  });

  const openMut = useMutation({
    mutationFn: (id: string) => consoleApi.get(id),
    onSuccess: (run) => {
      setCurrent(run);
      setTarget(run.target);
      setText(run.input_text);
      setMask(run.masked);
    },
    onError: () => notification.error({ title: 'Не удалось открыть запуск' }),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => consoleApi.remove(id),
    onSuccess: (_, id) => {
      if (current?.id === id) setCurrent(null);
      qc.invalidateQueries({ queryKey: ['admin', 'console-runs'] });
    },
    onError: () => notification.error({ title: 'Не удалось удалить запуск' }),
  });

  const addPreset = (lines: string[]) =>
    setText((prev) => (prev.trim() ? `${prev.replace(/\s+$/, '')}\n` : '') + lines.join('\n'));

  const copy = async () => {
    if (!current) return;
    const ok = await copyText(current.output_text);
    if (ok) notification.success({ title: 'Результат скопирован' });
    else notification.error({ title: 'Не удалось скопировать — скачайте файлом' });
  };

  const columns = [
    { title: 'Когда', dataIndex: 'created_at', width: 170, render: (v: string) => fmt(v) },
    { title: 'Кто', dataIndex: 'user_name', width: 180 },
    { title: 'Система', dataIndex: 'target', width: 110, render: (v: ConsoleTarget) => TITLES[v] },
    {
      title: 'Запросов',
      width: 140,
      render: (_: unknown, r: ConsoleRunBrief) =>
        `${r.request_count}${r.error_count ? `, ошибок ${r.error_count}` : ''}`,
    },
    { title: 'Запрос', dataIndex: 'first_line', ellipsis: true },
    {
      title: '',
      width: 170,
      render: (_: unknown, r: ConsoleRunBrief) => (
        <Space>
          <Button size="small" onClick={() => openMut.mutate(r.id)}>Открыть</Button>
          <Popconfirm title="Удалить запуск из истории?" onConfirm={() => deleteMut.mutate(r.id)}>
            <Button size="small" icon={<DeleteOutlined />} aria-label="Удалить" />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Space orientation="vertical" size="large" style={{ width: '100%' }}>
      <Paragraph type="secondary" style={{ marginBottom: 0 }}>
        Сервер отправляет запросы на чтение своим токеном и показывает ответы одним текстом.
        Одна строка — один запрос: ссылка из браузера или её часть после адреса системы.
        Строки с «#» — пояснения. Изменить что-либо в Jira или Confluence отсюда нельзя.
      </Paragraph>

      <Space wrap>
        <Segmented
          value={target}
          onChange={(v) => setTarget(v as ConsoleTarget)}
          options={[{ value: 'jira', label: 'Jira' }, { value: 'confluence', label: 'Confluence' }]}
        />
        {PRESETS[target].map((p) => (
          <Button key={p.label} size="small" onClick={() => addPreset(p.lines)}>{p.label}</Button>
        ))}
      </Space>

      <Input.TextArea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={10}
        placeholder={'/rest/api/2/serverInfo\n# поля задач\n/rest/api/2/field'}
        style={{ fontFamily: 'monospace' }}
      />

      <Space wrap>
        <Button
          type="primary"
          icon={<PlayCircleOutlined />}
          loading={runMut.isPending}
          disabled={!text.trim()}
          onClick={() => runMut.mutate()}
        >
          Выполнить
        </Button>
        <Checkbox checked={mask} onChange={(e) => setMask(e.target.checked)}>
          Скрыть имена и почту
        </Checkbox>
      </Space>

      {runMut.isPending && (
        <Alert type="info" showIcon title="Запросы выполняются по очереди — это может занять до полутора минут" />
      )}

      {current && (
        <Space orientation="vertical" style={{ width: '100%' }}>
          <Space wrap>
            <Text strong>Результат от {fmt(current.created_at)}</Text>
            <Button icon={<CopyOutlined />} onClick={copy}>Скопировать всё</Button>
            <Button icon={<DownloadOutlined />} onClick={() => downloadRun(current)}>Скачать файлом</Button>
          </Space>
          <Input.TextArea
            value={current.output_text}
            readOnly
            rows={24}
            style={{ fontFamily: 'monospace' }}
          />
        </Space>
      )}

      <div>
        <Text strong>История (последние 30 запусков)</Text>
        <Table
          rowKey="id"
          size="small"
          loading={history.isLoading}
          columns={columns}
          dataSource={history.data?.items ?? []}
          pagination={false}
          style={{ marginTop: 8 }}
        />
      </div>
    </Space>
  );
}
