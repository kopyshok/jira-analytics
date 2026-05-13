import { useState } from 'react';
import { Button, Input, Space, Tag, Typography } from 'antd';
import { PlusOutlined } from '@ant-design/icons';
import { DARK_THEME } from '../../utils/constants';
import { useAddThemeAlias, useRemoveThemeAlias } from '../../hooks/useThemeDictionary';

interface Props {
  themeId: string;
  aliases: string[];
  readOnly?: boolean;
}

export default function ThemeAliasesEditor({ themeId, aliases, readOnly }: Props) {
  const [draft, setDraft] = useState('');
  const addMutation = useAddThemeAlias();
  const removeMutation = useRemoveThemeAlias();

  const handleAdd = () => {
    const trimmed = draft.trim();
    if (!trimmed) return;
    addMutation.mutate(
      { themeId, alias: trimmed },
      { onSuccess: () => setDraft('') },
    );
  };

  return (
    <div>
      <Typography.Text
        style={{
          fontSize: 11,
          fontWeight: 700,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          color: DARK_THEME.textHint,
          display: 'block',
          marginBottom: 6,
        }}
      >
        Алиасы — синонимы темы для embedding-матчинга
      </Typography.Text>

      <Space size={[4, 8]} wrap style={{ marginBottom: readOnly ? 0 : 8, minHeight: 24 }}>
        {aliases.length === 0 && (
          <Typography.Text style={{ color: DARK_THEME.textMuted, fontSize: 12 }}>
            Алиасов нет. Добавьте синонимы — система будет автоматически относить
            похожие задачи к этой теме.
          </Typography.Text>
        )}
        {aliases.map((a) => (
          <Tag
            key={a}
            closable={!readOnly}
            onClose={(e) => {
              e.preventDefault();
              removeMutation.mutate({ themeId, alias: a });
            }}
            color="cyan"
          >
            {a}
          </Tag>
        ))}
      </Space>

      {!readOnly && (
        <Space.Compact style={{ width: '100%' }}>
          <Input
            value={draft}
            placeholder="Новый алиас, Enter — добавить"
            onChange={(e) => setDraft(e.target.value)}
            onPressEnter={handleAdd}
            maxLength={120}
            disabled={addMutation.isPending}
          />
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={handleAdd}
            disabled={!draft.trim() || addMutation.isPending}
          />
        </Space.Compact>
      )}
    </div>
  );
}
