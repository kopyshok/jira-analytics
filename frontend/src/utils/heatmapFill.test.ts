import { describe, it, expect } from 'vitest';
import { EXT_LOAD_COLOR, FREE_FILL, splitLoadFill } from './heatmapFill';

describe('splitLoadFill', () => {
  it('без других команд — прежняя заливка', () => {
    expect(splitLoadFill('X', 50, 0)).toBe('X');
  });
  it('снизу другие команды, выше этот план, остаток свободен', () => {
    expect(splitLoadFill('X', 30, 50)).toBe(
      `linear-gradient(to top, ${EXT_LOAD_COLOR} 0 50%, X 50% 80%, ${FREE_FILL} 80% 100%)`,
    );
  });
  it('перегруз — шкала по сумме, свободного нет', () => {
    expect(splitLoadFill('X', 100, 100)).toBe(
      `linear-gradient(to top, ${EXT_LOAD_COLOR} 0 50%, X 50% 100%, ${FREE_FILL} 100% 100%)`,
    );
  });
});
