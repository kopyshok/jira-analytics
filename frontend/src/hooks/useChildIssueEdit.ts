import { useQueryClient } from '@tanstack/react-query';
import { setIssueCategory, setIssueInclude } from '../api/issues';

const ARCHIVE_CODES = new Set(['archive', 'archive_target']);

/** Архивная категория снимает задачу с анализа сама — галочку не трогают. */
export function isArchiveCategory(code: string | null | undefined): boolean {
  return ARCHIVE_CODES.has(code ?? '');
}

/**
 * Правка подзадачи прямо из карточки задачи: категория и признак «в анализ».
 * После сохранения обновляются дерево задач, отчёт и контекст подзадачи.
 */
export function useChildIssueEdit(childId: string, onSaved: () => void) {
  const qc = useQueryClient();

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ['issues', 'tree'] });
    qc.invalidateQueries({ queryKey: ['analytics-report'] });
    qc.invalidateQueries({ queryKey: ['issue', 'context', childId] });
    onSaved();
  };

  const changeCategory = async (code: string | null) => {
    await setIssueCategory(childId, code);
    refresh();
  };

  const changeInclude = async (checked: boolean) => {
    await setIssueInclude(childId, checked);
    refresh();
  };

  return { changeCategory, changeInclude };
}
