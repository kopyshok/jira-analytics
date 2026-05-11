import { useAppTheme } from '../contexts/ThemeContext';
import { THEME_TOKENS_V2, type ThemeTokensV2 } from '../utils/constants';

/**
 * Возвращает токены текущей темы. Реактивно: при смене темы компонент
 * ре-рендерится с новыми значениями.
 *
 * Использование:
 * ```ts
 * const t = useThemeTokens();
 * <div style={{ background: t.surface.card, color: t.text.primary }} />
 * ```
 *
 * Параллельная архитектура к DARK_THEME (legacy flat const). Новый и
 * мигрируемый код использует этот хук, существующий код продолжает
 * импортировать DARK_THEME до постепенной миграции.
 */
export function useThemeTokens(): ThemeTokensV2 {
  const { theme } = useAppTheme();
  return THEME_TOKENS_V2[theme];
}
