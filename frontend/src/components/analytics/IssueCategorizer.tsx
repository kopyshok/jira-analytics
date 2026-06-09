import { useState } from 'react';
import { Select, Checkbox, Switch, Button, Alert, Tooltip } from 'antd';
import { useQueryClient } from '@tanstack/react-query';
import type { CategoryResponse } from '../../types/api';
import type { IssueContextResponse } from '../../types/api';
import { setIssueCategory, setIssueInclude, batchSetCategory } from '../../api/issues';
import { trackAction } from '../../lib/usage/track';

const ARCHIVE_CODES = new Set(['archive', 'archive_target']);

const CARD_BG = 'rgba(255,255,255,0.03)';
const CARD_BORDER = '1px solid rgba(255,255,255,0.08)';

interface Props {
  context: IssueContextResponse;
  categories: CategoryResponse[];
  onSaved: () => void;
}

export default function IssueCategorizer({ context, categories, onSaved }: Props) {
  const qc = useQueryClient();
  const [selectedCategory, setSelectedCategory] = useState<string | null>(
    context.assigned_category ?? null,
  );
  const [includeInAnalysis, setIncludeInAnalysis] = useState(context.include_in_analysis);
  const [applyToSubtree, setApplyToSubtree] = useState(false);
  const [saving, setSaving] = useState(false);

  const isArchive = ARCHIVE_CODES.has(selectedCategory ?? '');
  const subtreeN = context.subtree_count - 1; // потомки без текущей задачи

  const invalidate = (id: string) => {
    qc.invalidateQueries({ queryKey: ['issues', 'tree'] });
    qc.invalidateQueries({ queryKey: ['analytics-report'] });
    qc.invalidateQueries({ queryKey: ['issue', 'context', id] });
    // Инвалидируем контекст предков (для drill-back)
    for (const anc of context.ancestors) {
      qc.invalidateQueries({ queryKey: ['issue', 'context', anc.id] });
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      if (applyToSubtree && context.subtree_count > 1) {
        // Батч: текущая + все потомки через batch-category
        // Собираем ID поддерева из children (до 50 прямых) + рекурсивно
        // Простой подход: ставим категорию через batch по всем children + root
        const allIds = collectSubtreeIds(context);
        await batchSetCategory(allIds, selectedCategory);
        // include — применяем к root рекурсивно
        await setIssueInclude(context.id, includeInAnalysis, true);
      } else {
        await setIssueCategory(context.id, selectedCategory);
        await setIssueInclude(context.id, includeInAnalysis);
      }
      trackAction('category_changed', context.id);
      invalidate(context.id);
      onSaved();
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setSelectedCategory(context.assigned_category ?? null);
    setIncludeInAnalysis(context.include_in_analysis);
    setApplyToSubtree(false);
  };

  // Effective категория: ручная override либо унаследованная от родителя
  // (CategoryResolver). Показываем effective чтобы синхронизировать с
  // иерархическим отчётом — иначе юзер видит «Без категории» хотя задача
  // в отчёте под категорией предка.
  const effectiveCode = context.assigned_category ?? context.category ?? null;
  const isInherited = !context.assigned_category && context.category != null;
  const effectiveCat = categories.find(c => c.code === effectiveCode);
  const effectiveLabel = effectiveCat?.label ?? (effectiveCode ?? 'Без категории');

  return (
    <div
      style={{
        background: CARD_BG,
        border: CARD_BORDER,
        borderRadius: 8,
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          color: 'var(--text-muted, #64748b)',
          padding: '10px 14px 8px',
          borderBottom: '1px solid rgba(255,255,255,0.06)',
        }}
      >
        Категория и анализ
      </div>
      <div style={{ padding: '12px 14px' }}>
        {context.is_container && (
          <Alert
            type="warning"
            showIcon
            icon={<span>⚠</span>}
            title="Это контейнер. Категории ставятся детям, не самому контейнеру."
            style={{
              marginBottom: 12,
              background: 'rgba(251,191,36,0.07)',
              border: '1px solid rgba(251,191,36,0.18)',
              borderRadius: 6,
              color: '#fbbf24',
              fontSize: 11,
            }}
          />
        )}

        {/* Current → new category */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12, flexWrap: 'wrap' }}>
          <Tooltip
            title={
              isInherited
                ? 'Категория унаследована от родительской задачи. Можно поставить свою — она перекроет наследование.'
                : undefined
            }
          >
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 6,
                fontSize: 11,
                fontWeight: 500,
                padding: '3px 9px',
                borderRadius: 10,
                background: isInherited ? 'rgba(34,211,238,0.08)' : 'rgba(100,116,139,0.12)',
                color: isInherited ? '#67e8f9' : 'var(--text-muted, #94a3b8)',
                border: isInherited
                  ? '1px solid rgba(34,211,238,0.25)'
                  : '1px solid rgba(100,116,139,0.2)',
                whiteSpace: 'nowrap',
                cursor: isInherited ? 'help' : 'default',
              }}
            >
              {effectiveCat?.color && (
                <span
                  style={{
                    width: 7,
                    height: 7,
                    borderRadius: '50%',
                    background: effectiveCat.color,
                    display: 'inline-block',
                  }}
                />
              )}
              {effectiveLabel}
              {isInherited && (
                <span style={{ fontSize: 9, opacity: 0.75, marginLeft: 2 }}>унасл.</span>
              )}
            </span>
          </Tooltip>
          <span style={{ color: 'var(--text-muted, #475569)', fontSize: 13 }}>→</span>
          <Select
            disabled={context.is_container}
            value={selectedCategory}
            onChange={(val) => {
              setSelectedCategory(val ?? null);
              if (ARCHIVE_CODES.has(val ?? '')) {
                setIncludeInAnalysis(false);
              }
            }}
            allowClear
            placeholder="Без категории"
            style={{ minWidth: 220 }}
            options={categories.map(c => ({
              value: c.code,
              label: (
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                  <span
                    style={{
                      width: 8,
                      height: 8,
                      borderRadius: '50%',
                      background: c.color ?? 'var(--text-muted, #64748b)',
                      flexShrink: 0,
                      display: 'inline-block',
                    }}
                  />
                  {c.label}
                </span>
              ),
            }))}
          />
        </div>

        {/* Include in analysis */}
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 10 }}>
          <Tooltip
            title={isArchive ? 'Снимается автоматически архивной категорией' : undefined}
          >
            <Checkbox
              disabled={context.is_container || isArchive}
              checked={includeInAnalysis}
              onChange={e => setIncludeInAnalysis(e.target.checked)}
            >
              <span style={{ fontSize: 12, color: isArchive ? 'var(--text-muted, #475569)' : '#cbd5e1' }}>
                Учитывать в анализе
              </span>
              {isArchive && (
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 5,
                    fontSize: 11,
                    color: 'var(--text-muted, #475569)',
                    background: 'rgba(100,116,139,0.08)',
                    border: '1px solid rgba(100,116,139,0.15)',
                    borderRadius: 5,
                    padding: '2px 8px',
                    marginLeft: 6,
                  }}
                >
                  ⓘ снимается автоматически архивной категорией
                </span>
              )}
            </Checkbox>
          </Tooltip>
        </div>

        {/* Subtree toggle (shown only when has descendants) */}
        {context.subtree_count > 1 && !context.is_container && (
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 8 }}>
            <Switch
              size="small"
              checked={applyToSubtree}
              onChange={setApplyToSubtree}
              style={{ marginTop: 2, flexShrink: 0 }}
            />
            <div>
              <div style={{ fontSize: 12, color: 'var(--text-muted, #94a3b8)', lineHeight: 1.4 }}>
                Применить ко всему поддереву{' '}
                <span style={{ color: 'var(--text-muted, #64748b)' }}>({subtreeN} {subtreeN === 1 ? 'задача' : subtreeN < 5 ? 'задачи' : 'задач'})</span>
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-muted, #475569)', fontStyle: 'italic', marginTop: 2 }}>
                Категория поставится на эту задачу + всех детей рекурсивно
              </div>
            </div>
          </div>
        )}

        {/* Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'flex-end', marginTop: 12 }}>
          <Button
            size="small"
            onClick={handleCancel}
            disabled={saving}
            style={{
              background: 'rgba(255,255,255,0.05)',
              border: '1px solid rgba(255,255,255,0.1)',
              color: 'var(--text-muted, #94a3b8)',
            }}
          >
            Отмена
          </Button>
          <Button
            size="small"
            type="primary"
            loading={saving}
            disabled={context.is_container}
            onClick={handleSave}
            style={{
              background: '#00c9c8',
              borderColor: '#00c9c8',
              color: '#0d1c33',
              fontWeight: 600,
            }}
          >
            Сохранить
          </Button>
        </div>
      </div>
    </div>
  );
}

/**
 * Collect all issue IDs from the context's loaded subtree (root + all children recursively).
 * Since context.children is already loaded (up to 50), we include them all.
 */
function collectSubtreeIds(context: IssueContextResponse): string[] {
  const ids: string[] = [context.id];
  for (const child of context.children) {
    ids.push(child.id);
  }
  return ids;
}
