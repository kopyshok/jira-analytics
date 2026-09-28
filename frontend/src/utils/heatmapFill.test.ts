import { describe, it, expect } from 'vitest';
import { EXT_LOAD_COLOR, FREE_FILL, OTHER_WORK_COLOR, quarterLoad, splitLoadFill } from './heatmapFill';

describe('splitLoadFill', () => {
  it('без других команд — прежняя заливка', () => {
    expect(splitLoadFill('X', 50, 0)).toBe('X');
  });
  it('снизу другие команды, выше этот план, остаток свободен', () => {
    expect(splitLoadFill('X', 30, 50)).toBe(
      `linear-gradient(to top, ${EXT_LOAD_COLOR} 0 50%, X 50% 80%, ${OTHER_WORK_COLOR} 80% 80%, ${FREE_FILL} 80% 100%)`,
    );
  });
  it('перегруз — шкала по сумме, свободного нет', () => {
    expect(splitLoadFill('X', 100, 100)).toBe(
      `linear-gradient(to top, ${EXT_LOAD_COLOR} 0 50%, X 50% 100%, ${OTHER_WORK_COLOR} 100% 100%, ${FREE_FILL} 100% 100%)`,
    );
  });
  it('прочие работы — над часами задач, под свободным', () => {
    expect(splitLoadFill('X', 90, 0, 10)).toBe(
      `linear-gradient(to top, ${EXT_LOAD_COLOR} 0 0%, X 0% 90%, ${OTHER_WORK_COLOR} 90% 100%, ${FREE_FILL} 100% 100%)`,
    );
  });
});

describe('quarterLoad', () => {
  it('средняя загрузка по рабочим дням: этот план, другие команды и прочие работы', () => {
    const days = [
      { pct: 90, ext_pct: 0, other_pct: 10 },
      { pct: 0, ext_pct: 90, other_pct: 10 },
      { pct: 0 },
      { pct: 0 },
      { pct: 100, off: 'absence' as const },
    ];
    expect(quarterLoad(days)).toEqual({ own: 23, ext: 23, other: 5, total: 50, free: 50 });
  });
  it('перегруз — свободного нет', () => {
    expect(quarterLoad([{ pct: 100, ext_pct: 50 }])).toEqual({ own: 100, ext: 50, other: 0, total: 150, free: 0 });
  });
  it('нет рабочих дней — нули', () => {
    expect(quarterLoad([])).toEqual({ own: 0, ext: 0, other: 0, total: 0, free: 0 });
  });
});
