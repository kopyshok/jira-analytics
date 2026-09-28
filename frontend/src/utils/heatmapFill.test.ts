import { describe, it, expect } from 'vitest';
import { EXT_LOAD_COLOR, FREE_FILL, NORMED_WORK_COLOR, splitLoadFill } from './heatmapFill';

describe('splitLoadFill', () => {
  it('без других команд и нормированных работ — прежняя заливка', () => {
    expect(splitLoadFill('X', 50, 0)).toBe('X');
  });
  it('снизу другие команды, выше этот план, остаток свободен', () => {
    expect(splitLoadFill('X', 30, 50)).toBe(
      `linear-gradient(to top, ${EXT_LOAD_COLOR} 0 50%, X 50% 80%, ${NORMED_WORK_COLOR} 80% 80%, ${FREE_FILL} 80% 100%)`,
    );
  });
  it('перегруз — шкала по сумме, свободного нет', () => {
    expect(splitLoadFill('X', 100, 100)).toBe(
      `linear-gradient(to top, ${EXT_LOAD_COLOR} 0 50%, X 50% 100%, ${NORMED_WORK_COLOR} 100% 100%, ${FREE_FILL} 100% 100%)`,
    );
  });
  it('нормированные работы — над часами задач, под свободным', () => {
    expect(splitLoadFill('X', 90, 0, 10)).toBe(
      `linear-gradient(to top, ${EXT_LOAD_COLOR} 0 0%, X 0% 90%, ${NORMED_WORK_COLOR} 90% 100%, ${FREE_FILL} 100% 100%)`,
    );
  });
});
