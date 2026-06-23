import { useState } from 'react';
import {
  Button, Table, Form, Input, Modal, Select, Space, Popconfirm,
  App, Switch, Tag, Collapse, Empty,
} from 'antd';
import type { ColumnsType } from 'antd/es/table';
import {
  PlusOutlined, DeleteOutlined, EditOutlined, EyeOutlined, RocketOutlined,
  ReloadOutlined,
} from '@ant-design/icons';
import {
  useDraftReleaseNotes, useAllReleaseNotes,
  useCreateReleaseNote, useUpdateReleaseNote, useDeleteReleaseNote,
  usePublishReleaseNotes, useDeleteVersion, useReseedReleaseNotes,
} from '../../hooks/useReleaseNotes';
import {
  NOTE_TYPE_LABELS, NOTE_TYPE_COLORS, SECTION_LABELS,
} from '../../types/releaseNotes';
import type {
  ReleaseNote, ReleaseNoteCreate, ReleaseNoteUpdate, ReleaseNoteType, ReleaseSection,
} from '../../types/releaseNotes';
import WhatsNewModal from '../release-notes/WhatsNewModal';

export default function ReleaseNotesAdminTab() {
  const { notification } = App.useApp();
  const drafts = useDraftReleaseNotes();
  const all = useAllReleaseNotes();
  const createMut = useCreateReleaseNote();
  const updateMut = useUpdateReleaseNote();
  const deleteMut = useDeleteReleaseNote();
  const publishMut = usePublishReleaseNotes();
  const deleteVersionMut = useDeleteVersion();
  const reseedMut = useReseedReleaseNotes();

  const handleReseed = () => {
    reseedMut.mutate(undefined, {
      onSuccess: (s) => {
        notification.success({
          title: 'Заметки загружены в сервис',
          description:
            `Файлов: ${s.files}. Новых: ${s.created}, обновлено: ${s.updated}, ` +
            `без изменений: ${s.unchanged}.`,
        });
      },
      onError: () => {
        notification.error({ title: 'Не удалось загрузить заметки' });
      },
    });
  };

  const [editing, setEditing] = useState<ReleaseNote | null>(null);
  const [adding, setAdding] = useState(false);
  const [publishOpen, setPublishOpen] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [publishVersion, setPublishVersion] = useState('');

  const columns: ColumnsType<ReleaseNote> = [
    {
      title: 'Тип', dataIndex: 'note_type', width: 130,
      render: (t: ReleaseNoteType) => (
        <Tag color={NOTE_TYPE_COLORS[t]}>{NOTE_TYPE_LABELS[t]}</Tag>
      ),
    },
    {
      title: 'Раздел', dataIndex: 'section', width: 140,
      render: (s: ReleaseSection) => SECTION_LABELS[s],
    },
    { title: 'Заголовок', dataIndex: 'title' },
    {
      title: 'Скрыт?', dataIndex: 'is_hidden', width: 80,
      render: (h: boolean, row: ReleaseNote) => (
        <Switch
          checked={h}
          onChange={(v) => updateMut.mutate({ id: row.id, body: { is_hidden: v } })}
        />
      ),
    },
    {
      title: '', key: 'actions', width: 100,
      render: (_: unknown, row: ReleaseNote) => (
        <Space>
          <Button
            size="small" icon={<EditOutlined />}
            onClick={() => setEditing(row)}
          />
          <Popconfirm
            title="Удалить запись?"
            onConfirm={() => deleteMut.mutate(row.id)}
          >
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <Button icon={<PlusOutlined />} onClick={() => setAdding(true)}>
          Добавить запись
        </Button>
        <Button
          icon={<EyeOutlined />}
          onClick={() => setPreviewOpen(true)}
          disabled={!drafts.data || drafts.data.length === 0}
        >
          Посмотреть как пользователь
        </Button>
        <Button
          type="primary"
          icon={<RocketOutlined />}
          onClick={() => setPublishOpen(true)}
          disabled={!drafts.data || drafts.data.length === 0}
        >
          Выпустить под версию…
        </Button>
        <Button
          icon={<ReloadOutlined />}
          loading={reseedMut.isPending}
          onClick={handleReseed}
        >
          Загрузить заметки в сервис
        </Button>
      </Space>

      <h3>Готовится к выпуску ({drafts.data?.length ?? 0})</h3>
      <Table
        size="small"
        rowKey="id"
        loading={drafts.isLoading}
        dataSource={drafts.data ?? []}
        columns={columns}
        pagination={false}
        locale={{ emptyText: 'Черновиков нет — добавь через «Добавить запись»' }}
      />

      <h3 style={{ marginTop: 32 }}>История версий</h3>
      {(!all.data || all.data.feeds.length === 0) ? (
        <Empty description="Нет опубликованных версий" />
      ) : (
        <Collapse
          items={all.data.feeds.map((feed) => ({
            key: feed.version,
            label: (
              <Space>
                <strong>{feed.version}</strong>
                <span style={{ color: '#888' }}>({feed.notes.length} зап.)</span>
              </Space>
            ),
            children: (
              <>
                <Table
                  size="small"
                  rowKey="id"
                  dataSource={feed.notes}
                  columns={columns}
                  pagination={false}
                />
                <Popconfirm
                  title={`Откатить версию ${feed.version}?`}
                  description="Записи вернутся в черновики, версия исчезнет из ленты"
                  onConfirm={() =>
                    deleteVersionMut.mutate(feed.version, {
                      onSuccess: () =>
                        notification.success({
                          title: `Версия ${feed.version} возвращена в черновики`,
                        }),
                    })
                  }
                >
                  <Button danger size="small" style={{ marginTop: 8 }} icon={<DeleteOutlined />}>
                    Откатить версию
                  </Button>
                </Popconfirm>
              </>
            ),
          }))}
        />
      )}

      <NoteEditor
        open={adding || editing !== null}
        initial={editing ?? undefined}
        onSubmit={(body) => {
          if (editing) {
            updateMut.mutate(
              { id: editing.id, body },
              {
                onSuccess: () => {
                  setEditing(null);
                  notification.success({ title: 'Сохранено' });
                },
              },
            );
          } else {
            createMut.mutate(body as ReleaseNoteCreate, {
              onSuccess: () => {
                setAdding(false);
                notification.success({ title: 'Добавлено' });
              },
            });
          }
        }}
        onCancel={() => { setAdding(false); setEditing(null); }}
      />

      <Modal
        title="Выпустить под версию"
        open={publishOpen}
        onCancel={() => setPublishOpen(false)}
        onOk={() => {
          if (!publishVersion) return;
          publishMut.mutate(publishVersion, {
            onSuccess: (res) => {
              setPublishOpen(false);
              setPublishVersion('');
              notification.success({
                title: `Опубликовано ${res.published_count} зап. под ${res.version}`,
              });
            },
            onError: (err: unknown) => {
              const msg =
                err && typeof err === 'object' && 'message' in err
                  ? String((err as { message?: unknown }).message ?? '')
                  : '';
              notification.error({ title: 'Не удалось опубликовать', description: msg });
            },
          });
        }}
        okButtonProps={{ disabled: !publishVersion }}
      >
        <p style={{ marginTop: 0 }}>
          Все черновики получат указанную версию и появятся в ленте «Что нового» у пользователей.
        </p>
        <Input
          placeholder="v1.2.0"
          value={publishVersion}
          onChange={(e) => setPublishVersion(e.target.value)}
        />
      </Modal>

      <WhatsNewModal
        open={previewOpen}
        feeds={[{ version: 'Предпросмотр', notes: drafts.data ?? [] }]}
        onClose={() => setPreviewOpen(false)}
        onMarkSeen={() => {}}
      />
    </div>
  );
}

interface NoteEditorProps {
  open: boolean;
  initial?: ReleaseNote;
  onSubmit: (body: ReleaseNoteCreate | ReleaseNoteUpdate) => void;
  onCancel: () => void;
}

function NoteEditor({ open, initial, onSubmit, onCancel }: NoteEditorProps) {
  const [form] = Form.useForm();
  return (
    <Modal
      open={open}
      onCancel={onCancel}
      onOk={async () => {
        const values = await form.validateFields();
        onSubmit(values);
      }}
      title={initial ? 'Редактировать запись' : 'Добавить запись'}
      destroyOnHidden
      width={640}
    >
      <Form
        form={form}
        layout="vertical"
        initialValues={initial ?? { note_type: 'new', section: 'general' }}
        preserve={false}
      >
        <Form.Item label="Тип" name="note_type" rules={[{ required: true }]}>
          <Select
            options={(Object.keys(NOTE_TYPE_LABELS) as ReleaseNoteType[]).map((k) => ({
              value: k, label: NOTE_TYPE_LABELS[k],
            }))}
          />
        </Form.Item>
        <Form.Item label="Раздел" name="section" rules={[{ required: true }]}>
          <Select
            options={(Object.keys(SECTION_LABELS) as ReleaseSection[]).map((k) => ({
              value: k, label: SECTION_LABELS[k],
            }))}
          />
        </Form.Item>
        <Form.Item label="Заголовок" name="title" rules={[{ required: true }]}>
          <Input maxLength={500} />
        </Form.Item>
        <Form.Item label="Описание" name="description" rules={[{ required: true }]}>
          <Input.TextArea rows={4} />
        </Form.Item>
        <Form.Item label="Ссылка на справку (опционально)" name="help_link">
          <Input placeholder="https://… или путь в приложении" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
