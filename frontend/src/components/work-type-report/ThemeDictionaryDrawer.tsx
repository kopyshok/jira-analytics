import { useState } from 'react';
import {
  Button,
  ColorPicker,
  Drawer,
  Dropdown,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Select,
  Table,
  Tabs,
  Tag,
  Tooltip,
  Typography,
} from 'antd';
import type { TableColumnsType } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { DARK_THEME } from '../../utils/constants';
import {
  useThemeList,
  useCreateTheme,
  useUpdateTheme,
  useArchiveTheme,
  useRestoreTheme,
  useMergeThemes,
} from '../../hooks/useThemeDictionary';
import {
  useAcceptCandidate,
  useMergeCandidate,
  useIgnoreCandidate,
} from '../../hooks/useWorkTypeReport';
import type { ThemeOut, Candidate } from '../../types/workTypeReport';
import ThemeAliasesEditor from './ThemeAliasesEditor';
import EmbeddingThresholdSlider from './EmbeddingThresholdSlider';

interface Props {
  open: boolean;
  workTypeId: string;
  initialTab?: 'active' | 'archived' | 'candidates';
  candidates: Candidate[];
  snapshotId: string | null;
  onClose: () => void;
}

// ---- Edit / Create modal inner content (remounted on each open) ----

interface ThemeEditModalContentProps {
  initial: Partial<ThemeOut>;
  workTypeId: string;
  isCreate: boolean;
  onClose: () => void;
}

function ThemeEditModalContent({ initial, workTypeId, isCreate, onClose }: ThemeEditModalContentProps) {
  const [name, setName] = useState(initial.name ?? '');
  const [description, setDescription] = useState(initial.description ?? '');
  const [color, setColor] = useState<string>(initial.color ?? DARK_THEME.cyanPrimary);
  const [sortOrder, setSortOrder] = useState<number>(initial.sort_order ?? 0);

  const createMutation = useCreateTheme();
  const updateMutation = useUpdateTheme();
  const isPending = createMutation.isPending || updateMutation.isPending;

  const handleOk = () => {
    if (!name.trim()) return;
    if (isCreate) {
      createMutation.mutate(
        { work_type_id: workTypeId, name: name.trim(), description: description || null, color, sort_order: sortOrder },
        { onSuccess: onClose },
      );
    } else if (initial.id) {
      updateMutation.mutate(
        { themeId: initial.id, body: { name: name.trim(), description: description || null, color, sort_order: sortOrder } },
        { onSuccess: onClose },
      );
    }
  };

  return (
    <Modal
      open
      title={isCreate ? 'Создать тему' : 'Редактировать тему'}
      okText={isCreate ? 'Создать' : 'Сохранить'}
      cancelText="Отмена"
      confirmLoading={isPending}
      onOk={handleOk}
      onCancel={onClose}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 8 }}>
        <div>
          <Typography.Text style={{ fontSize: 12, color: DARK_THEME.textMuted }}>Название *</Typography.Text>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Название темы"
            style={{ marginTop: 4 }}
          />
        </div>
        <div>
          <Typography.Text style={{ fontSize: 12, color: DARK_THEME.textMuted }}>Описание</Typography.Text>
          <Input.TextArea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={3}
            placeholder="Краткое описание темы"
            style={{ marginTop: 4 }}
          />
        </div>
        <div style={{ display: 'flex', gap: 16 }}>
          <div>
            <Typography.Text style={{ fontSize: 12, color: DARK_THEME.textMuted, display: 'block' }}>Цвет</Typography.Text>
            <ColorPicker
              value={color}
              onChange={(value) => setColor(value.toHexString())}
              style={{ marginTop: 4 }}
            />
          </div>
          <div>
            <Typography.Text style={{ fontSize: 12, color: DARK_THEME.textMuted, display: 'block' }}>Порядок</Typography.Text>
            <InputNumber
              value={sortOrder}
              onChange={(v) => setSortOrder(v ?? 0)}
              min={0}
              style={{ marginTop: 4, width: 100 }}
            />
          </div>
        </div>
        {!isCreate && initial.id && (
          <ThemeAliasesEditor
            themeId={initial.id}
            aliases={initial.aliases ?? []}
          />
        )}
      </div>
    </Modal>
  );
}

// ---- Accept candidate modal inner content ----

interface AcceptModalContentProps {
  candidate: Candidate;
  snapshotId: string;
  onClose: () => void;
}

function AcceptModalContent({ candidate, snapshotId, onClose }: AcceptModalContentProps) {
  const [name, setName] = useState(candidate.proposed_name);
  const [color, setColor] = useState<string>(DARK_THEME.cyanPrimary);
  const mutation = useAcceptCandidate();

  const handleOk = () => {
    if (!name.trim()) return;
    mutation.mutate(
      { snapshot_id: snapshotId, proposed_name: candidate.proposed_name, new_theme_name: name.trim(), color },
      { onSuccess: onClose },
    );
  };

  return (
    <Modal
      open
      title="Принять кандидата"
      okText="Принять"
      cancelText="Отмена"
      confirmLoading={mutation.isPending}
      onOk={handleOk}
      onCancel={onClose}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12, marginTop: 8 }}>
        <div>
          <Typography.Text style={{ fontSize: 12, color: DARK_THEME.textMuted }}>Название темы</Typography.Text>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            style={{ marginTop: 4 }}
          />
        </div>
        <div>
          <Typography.Text style={{ fontSize: 12, color: DARK_THEME.textMuted, display: 'block' }}>Цвет</Typography.Text>
          <ColorPicker
            value={color}
            onChange={(value) => setColor(value.toHexString())}
            style={{ marginTop: 4 }}
          />
        </div>
      </div>
    </Modal>
  );
}

// ---- Merge candidate modal inner content ----

interface MergeCandidateModalContentProps {
  candidate: Candidate;
  snapshotId: string;
  themes: ThemeOut[];
  onClose: () => void;
}

function MergeCandidateModalContent({ candidate, snapshotId, themes, onClose }: MergeCandidateModalContentProps) {
  const [targetId, setTargetId] = useState<string | null>(null);
  const mutation = useMergeCandidate();

  const handleOk = () => {
    if (!targetId) return;
    mutation.mutate(
      { snapshot_id: snapshotId, proposed_name: candidate.proposed_name, target_theme_id: targetId },
      { onSuccess: onClose },
    );
  };

  return (
    <Modal
      open
      title="Слить кандидата с темой"
      okText="Слить"
      cancelText="Отмена"
      okButtonProps={{ disabled: !targetId }}
      confirmLoading={mutation.isPending}
      onOk={handleOk}
      onCancel={onClose}
    >
      <div style={{ marginTop: 8 }}>
        <Typography.Text style={{ fontSize: 12, color: DARK_THEME.textMuted, display: 'block', marginBottom: 6 }}>
          Выберите тему, в которую будет слит «{candidate.proposed_name}»:
        </Typography.Text>
        <Select
          style={{ width: '100%' }}
          placeholder="Выберите тему"
          value={targetId}
          onChange={setTargetId}
          options={themes.map((t) => ({ value: t.id, label: t.name }))}
        />
      </div>
    </Modal>
  );
}

// ---- Merge themes dropdown ----

interface MergeThemesDropdownProps {
  sourceTheme: ThemeOut;
  allThemes: ThemeOut[];
}

function MergeThemesDropdown({ sourceTheme, allThemes }: MergeThemesDropdownProps) {
  const mergeMutation = useMergeThemes();
  const targets = allThemes.filter((t) => t.id !== sourceTheme.id);

  const items = targets.map((t) => ({
    key: t.id,
    label: t.name,
  }));

  const handleMenuClick = ({ key }: { key: string }) => {
    mergeMutation.mutate({ themeId: sourceTheme.id, body: { target_theme_id: key } });
  };

  return (
    <Dropdown
      menu={{ items, onClick: handleMenuClick }}
      disabled={targets.length === 0 || mergeMutation.isPending}
      trigger={['click']}
    >
      <Button size="small" type="link" style={{ padding: 0 }}>
        Слить в...
      </Button>
    </Dropdown>
  );
}

// ---- Active themes tab ----

interface ActiveTabProps {
  workTypeId: string;
}

function ActiveTab({ workTypeId }: ActiveTabProps) {
  const { data, isLoading } = useThemeList(workTypeId, false);

  const archiveMutation = useArchiveTheme();

  // editModal: null = closed, otherwise { theme, isCreate }
  const [editModal, setEditModal] = useState<{ theme: Partial<ThemeOut>; isCreate: boolean } | null>(null);

  const themes = data?.themes ?? [];

  const columns: TableColumnsType<ThemeOut> = [
    {
      title: '',
      dataIndex: 'color',
      width: 32,
      render: (color: string) => (
        <div
          style={{
            width: 16,
            height: 16,
            borderRadius: '50%',
            background: color,
            flexShrink: 0,
          }}
        />
      ),
    },
    {
      title: 'Название',
      dataIndex: 'name',
      render: (name: string, rec) => (
        <Typography.Link
          onClick={() => setEditModal({ theme: rec, isCreate: false })}
          style={{ color: DARK_THEME.textPrimary }}
        >
          {name}
        </Typography.Link>
      ),
    },
    {
      title: 'Описание',
      dataIndex: 'description',
      ellipsis: true,
      render: (desc: string | null) =>
        desc ? (
          <Tooltip title={desc}>
            <span style={{ color: DARK_THEME.textMuted }}>{desc}</span>
          </Tooltip>
        ) : (
          <span style={{ color: DARK_THEME.textHint }}>—</span>
        ),
    },
    {
      title: '#',
      dataIndex: 'sort_order',
      width: 48,
      align: 'center',
    },
    {
      title: 'Действия',
      width: 160,
      render: (_, rec) => (
        <div style={{ display: 'flex', gap: 8 }}>
          <Popconfirm
            title="Архивировать тему?"
            okText="Да"
            cancelText="Нет"
            onConfirm={() => archiveMutation.mutate(rec.id)}
          >
            <Button size="small" type="link" danger style={{ padding: 0 }}>
              Архивировать
            </Button>
          </Popconfirm>
          <MergeThemesDropdown sourceTheme={rec} allThemes={themes} />
        </div>
      ),
    },
  ];

  return (
    <>
      <EmbeddingThresholdSlider />
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
        <Button
          icon={<PlusOutlined />}
          type="primary"
          size="small"
          onClick={() => setEditModal({ theme: {}, isCreate: true })}
        >
          Создать тему
        </Button>
      </div>
      <Table
        dataSource={themes}
        columns={columns}
        rowKey="id"
        size="small"
        loading={isLoading}
        pagination={false}
      />
      {/* Remount inner content on each open — avoids setState-in-effect */}
      {editModal && (
        <ThemeEditModalContent
          key={editModal.isCreate ? 'create' : (editModal.theme as ThemeOut).id}
          initial={editModal.theme}
          workTypeId={workTypeId}
          isCreate={editModal.isCreate}
          onClose={() => setEditModal(null)}
        />
      )}
    </>
  );
}

// ---- Archived themes tab ----

interface ArchivedTabProps {
  workTypeId: string;
}

function ArchivedTab({ workTypeId }: ArchivedTabProps) {
  const { data, isLoading } = useThemeList(workTypeId, true);
  const restoreMutation = useRestoreTheme();

  const themes = (data?.themes ?? []).filter((t) => t.is_archived);

  const columns: TableColumnsType<ThemeOut> = [
    {
      title: '',
      dataIndex: 'color',
      width: 32,
      render: (color: string) => (
        <div style={{ width: 16, height: 16, borderRadius: '50%', background: color, opacity: 0.5 }} />
      ),
    },
    {
      title: 'Название',
      dataIndex: 'name',
      render: (name: string) => (
        <Typography.Text style={{ color: DARK_THEME.textMuted }}>{name}</Typography.Text>
      ),
    },
    {
      title: 'Описание',
      dataIndex: 'description',
      ellipsis: true,
      render: (desc: string | null) =>
        desc ? (
          <Tooltip title={desc}>
            <span style={{ color: DARK_THEME.textHint }}>{desc}</span>
          </Tooltip>
        ) : (
          <span style={{ color: DARK_THEME.textHint }}>—</span>
        ),
    },
    {
      title: 'Действия',
      width: 120,
      render: (_, rec) => (
        <Button
          size="small"
          type="link"
          loading={restoreMutation.isPending}
          onClick={() => restoreMutation.mutate(rec.id)}
          style={{ padding: 0 }}
        >
          Восстановить
        </Button>
      ),
    },
  ];

  return (
    <Table
      dataSource={themes}
      columns={columns}
      rowKey="id"
      size="small"
      loading={isLoading}
      pagination={false}
    />
  );
}

// ---- Candidates tab ----

interface CandidatesTabProps {
  candidates: Candidate[];
  snapshotId: string | null;
  activeThemes: ThemeOut[];
}

function CandidatesTab({ candidates, snapshotId, activeThemes }: CandidatesTabProps) {
  const ignoreMutation = useIgnoreCandidate();

  // acceptModal / mergeModal: null = closed, otherwise the candidate
  const [acceptCandidate, setAcceptCandidate] = useState<Candidate | null>(null);
  const [mergeCandidate, setMergeCandidate] = useState<Candidate | null>(null);

  const disabled = snapshotId === null;

  if (candidates.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: '32px 0', color: DARK_THEME.textMuted }}>
        Нет кандидатов
      </div>
    );
  }

  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {candidates.map((c) => (
          <div
            key={c.proposed_name}
            style={{
              background: DARK_THEME.darkAccent,
              border: `1px solid ${DARK_THEME.border}`,
              borderRadius: 6,
              padding: '10px 12px',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8 }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <Typography.Text style={{ fontWeight: 600, color: DARK_THEME.textPrimary, display: 'block' }}>
                  {c.proposed_name}
                </Typography.Text>
                <Typography.Text style={{ fontSize: 12, color: DARK_THEME.textMuted }}>
                  {c.hours.toFixed(1)} ч · {c.issues_count} задач
                </Typography.Text>
                {c.sample_keys.length > 0 && (
                  <div style={{ marginTop: 4, display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                    {c.sample_keys.slice(0, 5).map((k) => (
                      <Tag key={k} style={{ fontSize: 11, margin: 0, padding: '0 4px', lineHeight: '18px' }}>
                        {k}
                      </Tag>
                    ))}
                  </div>
                )}
              </div>
              <div style={{ display: 'flex', gap: 6, flexShrink: 0 }}>
                <Tooltip title={disabled ? 'Снимок недоступен' : undefined}>
                  <Button
                    size="small"
                    type="primary"
                    disabled={disabled}
                    onClick={() => setAcceptCandidate(c)}
                  >
                    Принять
                  </Button>
                </Tooltip>
                <Tooltip title={disabled ? 'Снимок недоступен' : undefined}>
                  <Button
                    size="small"
                    disabled={disabled}
                    onClick={() => setMergeCandidate(c)}
                  >
                    Слить с
                  </Button>
                </Tooltip>
                <Popconfirm
                  title="Точно игнорировать?"
                  okText="Да"
                  cancelText="Нет"
                  disabled={disabled}
                  onConfirm={() => {
                    if (snapshotId) {
                      ignoreMutation.mutate({ snapshot_id: snapshotId, proposed_name: c.proposed_name });
                    }
                  }}
                >
                  <Tooltip title={disabled ? 'Снимок недоступен' : undefined}>
                    <Button size="small" danger disabled={disabled}>
                      Игнорировать
                    </Button>
                  </Tooltip>
                </Popconfirm>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Remount inner content on each selected candidate — avoids setState-in-effect */}
      {acceptCandidate && (
        <AcceptModalContent
          key={acceptCandidate.proposed_name}
          candidate={acceptCandidate}
          snapshotId={snapshotId ?? ''}
          onClose={() => setAcceptCandidate(null)}
        />
      )}
      {mergeCandidate && (
        <MergeCandidateModalContent
          key={mergeCandidate.proposed_name}
          candidate={mergeCandidate}
          snapshotId={snapshotId ?? ''}
          themes={activeThemes}
          onClose={() => setMergeCandidate(null)}
        />
      )}
    </>
  );
}

// ---- Main drawer ----

export default function ThemeDictionaryDrawer({
  open,
  workTypeId,
  initialTab = 'active',
  candidates,
  snapshotId,
  onClose,
}: Props) {
  // We need active themes for the candidate merge dropdown
  const { data: activeThemesData } = useThemeList(workTypeId, false);
  const activeThemes = activeThemesData?.themes ?? [];

  const items = [
    {
      key: 'active',
      label: 'Активные',
      children: open ? <ActiveTab workTypeId={workTypeId} /> : null,
    },
    {
      key: 'archived',
      label: 'Архивные',
      children: open ? <ArchivedTab workTypeId={workTypeId} /> : null,
    },
    {
      key: 'candidates',
      label: `Кандидаты${candidates.length > 0 ? ` (${candidates.length})` : ''}`,
      children: open ? (
        <CandidatesTab candidates={candidates} snapshotId={snapshotId} activeThemes={activeThemes} />
      ) : null,
    },
  ];

  return (
    <Drawer
      open={open}
      placement="right"
      width={720}
      title="Словарь тем"
      onClose={onClose}
      destroyOnHidden
      styles={{
        body: { padding: '12px 16px', background: DARK_THEME.pageBg },
        header: { background: DARK_THEME.cardBg, borderBottom: `1px solid ${DARK_THEME.border}` },
      }}
    >
      <Tabs
        key={open ? initialTab : 'closed'}
        defaultActiveKey={initialTab}
        items={items}
        size="small"
      />
    </Drawer>
  );
}
