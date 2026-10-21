import { describe, expect, it } from 'vitest';
import { silenceLabel } from './projectSilence';

describe('подпись «тишины» проекта', () => {
  it('часов не списывали ни разу — «списаний не было», а не «тишина 9999д»', () => {
    expect(silenceLabel(null, 14)).toBe('списаний не было');
  });

  it('молчит дольше порога — число дней', () => {
    expect(silenceLabel(21, 14)).toBe('тишина 21д');
  });

  it('списывали недавно — подписи нет', () => {
    expect(silenceLabel(14, 14)).toBeNull();
    expect(silenceLabel(0, 14)).toBeNull();
  });
});
