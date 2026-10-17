import { useState } from 'react';
import { Alert, Button, Checkbox, Select, Skeleton, Tag, Tooltip } from 'antd';
import { ArrowUpRight, X } from 'lucide-react';
import { useNavigate } from 'react-router';
import type { CategoryResponse, IssueContextChild } from '../../types/api';
import { useIssueContext } from '../../hooks/useIssueContext';
import { useIssueChildren } from '../../hooks/useIssueChildren';
import { useCategories } from '../../hooks/useCategories';
import { isArchiveCategory, useChildIssueEdit } from '../../hooks/useChildIssueEdit';
import { statusTagColor } from '../../utils/status';
import { formatIsoDate, isProjectCategory } from '../../utils/analyticsView';
import JiraIssueLink from '../shared/JiraIssueLink';
import IssueCategorizer from './IssueCategorizer';
import AnalyticsWorklogsBlock from './AnalyticsWorklogsBlock';

/** Соседей видно сразу столько; остальные — по «Показать все». */
const SIBLINGS_SHOWN = 5;

interface Props {
  issueId: string;
  issueKey: string;
  periodStart: string;
  periodEnd: string;
  canGoBack: boolean;
  onBack: () => void;
  onClose: () => void;
  onDrillDown: (id: string, key?: string) => void;
}

/**
 * Карточка задачи, встроенная в раскладку скина справа от отчёта (вместо
 * выезжающей шторки). Сверху — как в макете: ключ и статус, название, ссылка
 * на страницу проекта, категория и родитель, соседние задачи, ворклоги за
 * период. Ниже — то, что есть в шторке Aurora: подзадачи с правкой категории
 * и признака «в анализ», смена категории самой задачи.
 */
export default function AnalyticsIssuePanel({
  issueId, issueKey, periodStart, periodEnd, canGoBack, onBack, onClose, onDrillDown,
}: Props) {
  const { data: context, isLoading, isError, refetch } = useIssueContext(issueId);
  const { items: categories } = useCategories();
  const navigate = useNavigate();
  const [allSiblings, setAllSiblings] = useState(false);

  const ancestors = context?.ancestors ?? [];
  const parent = ancestors.length > 0 ? ancestors[ancestors.length - 1] : undefined;
  const upper = ancestors.slice(0, -1);
  const { data: siblingsData } = useIssueChildren(parent?.id, true);
  const siblings = (siblingsData ?? []).filter((s) => s.id !== issueId);
  const siblingsCount = context ? Math.max(0, context.siblings_total - 1) : siblings.length;

  const effectiveCode = context ? (context.assigned_category ?? context.category ?? null) : null;
  const effectiveCat = categories.find((c) => c.code === effectiveCode);
  const isInherited = !!context && !context.assigned_category && context.category != null;

  const keyButton = (id: string, key: string, title?: string) => (
    <button type="button" className="anc-keybtn" title={title} onClick={() => onDrillDown(id, key)}>
      {key}
    </button>
  );

  return (
    <aside className="wr-card anc-panel" aria-label="Задача">
      <div className="anc-panel-scroll">
        <div className="anc-panel-head">
          <div className="anc-panel-keys">
            {canGoBack && (
              <button type="button" className="anc-panel-back" onClick={onBack}>← назад</button>
            )}
            <JiraIssueLink issueKey={context?.key ?? issueKey} className="anc-panel-key">
              {context?.key ?? issueKey}
            </JiraIssueLink>
            {context && (
              <Tag color={statusTagColor(context.status, context.status_category)} className="anc-status">
                {context.status}
              </Tag>
            )}
          </div>
          <button type="button" className="anc-panel-close" aria-label="Закрыть" onClick={onClose}>
            <X size={16} aria-hidden />
          </button>
        </div>

        {isLoading ? (
          <Skeleton active paragraph={{ rows: 6 }} style={{ marginTop: 12 }} />
        ) : isError || !context ? (
          <Alert
            type="error"
            title="Не удалось загрузить контекст задачи"
            action={<Button size="small" onClick={() => refetch()}>Повторить</Button>}
            style={{ marginTop: 12 }}
          />
        ) : (
          <>
            <h2 className="anc-panel-title">{context.summary}</h2>
            {isProjectCategory(effectiveCode) && (
              <button
                type="button"
                className="anc-panel-link"
                onClick={() => navigate(`/projects/${encodeURIComponent(context.key)}`)}
              >
                Открыть страницу проекта <ArrowUpRight size={14} aria-hidden />
              </button>
            )}

            <div className="anc-panel-sec anc-facts">
              <div className="anc-fact">
                <span className="anc-fact-label">Категория:</span>
                <span className="anc-fact-value">
                  {effectiveCat?.color && <span className="anc-dot" style={{ background: effectiveCat.color }} />}
                  {effectiveCat?.label ?? effectiveCode ?? 'Без категории'}
                  {isInherited && <span className="anc-fact-note"> · унаследована</span>}
                </span>
              </div>
              <div className="anc-fact">
                <span className="anc-fact-label">Тип:</span>
                <span className="anc-fact-value">{context.issue_type}</span>
              </div>
              {parent && (
                <div className="anc-fact">
                  <span className="anc-fact-label">Родитель:</span>
                  <span className="anc-fact-value">
                    {keyButton(parent.id, parent.key)} {parent.summary}
                  </span>
                </div>
              )}
              {upper.length > 0 && (
                <div className="anc-fact">
                  <span className="anc-fact-label">Выше:</span>
                  <span className="anc-fact-value is-wrap">
                    {[...upper].reverse().map((a) => (
                      <span key={a.id}>{keyButton(a.id, a.key, a.summary)}</span>
                    ))}
                  </span>
                </div>
              )}
            </div>

            {parent && siblingsCount > 0 && (
              <div className="anc-panel-sec">
                <h3 className="anc-panel-h3">Соседние задачи ({siblingsCount})</h3>
                {(allSiblings ? siblings : siblings.slice(0, SIBLINGS_SHOWN)).map((s) => (
                  <div key={s.id} className="anc-sib">
                    {keyButton(s.id, s.key)}
                    <span className="anc-sib-summary" title={s.summary}>{s.summary}</span>
                  </div>
                ))}
                {siblings.length > SIBLINGS_SHOWN && (
                  <button type="button" className="wr-link anc-more" onClick={() => setAllSiblings((v) => !v)}>
                    {allSiblings ? 'Свернуть' : `Показать все (${siblings.length})`}
                  </button>
                )}
              </div>
            )}

            <div className="anc-panel-sec">
              <div className="anc-panel-h3row">
                <h3 className="anc-panel-h3">Ворклоги за период</h3>
                <span className="anc-panel-period">{formatIsoDate(periodStart)} – {formatIsoDate(periodEnd)}</span>
              </div>
              <AnalyticsWorklogsBlock
                compact
                issueId={issueId}
                periodStart={periodStart}
                periodEnd={periodEnd}
              />
            </div>

            {context.children.length > 0 && (
              <div className="anc-panel-sec">
                <h3 className="anc-panel-h3">Подзадачи ({context.children.length})</h3>
                {context.children.map((child) => (
                  <ChildItem
                    key={child.id}
                    child={child}
                    categories={categories}
                    onDrillDown={onDrillDown}
                  />
                ))}
              </div>
            )}

            <div className="anc-panel-sec">
              <IssueCategorizer compact context={context} categories={categories} onSaved={() => {}} />
            </div>
          </>
        )}
      </div>
    </aside>
  );
}

/** Подзадача: ключ, статус, название; ниже — категория и «в анализ», как в таблице шторки. */
function ChildItem({ child, categories, onDrillDown }: {
  child: IssueContextChild;
  categories: CategoryResponse[];
  onDrillDown: (id: string, key?: string) => void;
}) {
  const isArchive = isArchiveCategory(child.assigned_category);
  const { changeCategory, changeInclude } = useChildIssueEdit(child.id, () => {});
  return (
    <div className="anc-child">
      <div className="anc-child-line">
        <button type="button" className="anc-keybtn" onClick={() => onDrillDown(child.id, child.key)}>
          {child.key}
        </button>
        <Tag color={statusTagColor(child.status, child.status_category)} className="anc-status">
          {child.status}
        </Tag>
        <span className="anc-sib-summary" title={child.summary}>{child.summary}</span>
      </div>
      <div className="anc-child-line">
        <Select
          size="small"
          aria-label={`Категория ${child.key}`}
          value={child.assigned_category ?? null}
          onChange={changeCategory}
          allowClear
          placeholder="Без категории"
          className="anc-child-select"
          options={categories.map((c) => ({ value: c.code, label: c.label }))}
        />
        <Tooltip title={isArchive ? 'Снимается автоматически архивной категорией' : undefined}>
          <Checkbox
            checked={child.include_in_analysis}
            disabled={isArchive}
            onChange={(e) => changeInclude(e.target.checked)}
          >
            В анализ
          </Checkbox>
        </Tooltip>
      </div>
    </div>
  );
}
