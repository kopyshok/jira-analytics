import { describe, expect, it } from 'vitest';
import type { MultiTeamProgress, TeamTakeStatus } from '../types/api';
import {
  neighborsTaken, neighborsTakenTitle, progressTone, teamTakeLine,
} from './multiTeamProgress';

const progress = (
  own: string | null,
  statuses: Record<string, TeamTakeStatus>,
): MultiTeamProgress => {
  const teams = Object.entries(statuses).map(([team, status]) => ({ team, status, scenarios: [] }));
  return {
    taken: teams.filter((t) => t.status === 'taken').length,
    total: teams.length,
    own_team: own,
    own_status: own ? statuses[own] ?? null : null,
    teams,
  };
};

describe('progressTone', () => {
  it('никто не взял — серый', () => {
    expect(progressTone(progress('А', { А: 'not_taken', Б: 'no_epic' }))).toBe('none');
  });

  it('взяли все — зелёный', () => {
    expect(progressTone(progress('А', { А: 'taken', Б: 'taken' }))).toBe('done');
  });

  it('часть взяла: у не взявшей команды — яркий, у взявшей — нейтральный', () => {
    const statuses = { А: 'taken', Б: 'not_taken', В: 'no_epic' } as const;
    expect(progressTone(progress('Б', statuses))).toBe('alert');
    expect(progressTone(progress('В', statuses))).toBe('alert');
    expect(progressTone(progress('А', statuses))).toBe('neutral');
  });

  it('команда строки не участник — нейтральный', () => {
    expect(progressTone(progress(null, { А: 'taken', Б: 'not_taken' }))).toBe('neutral');
  });
});

describe('neighborsTaken', () => {
  it('взяла другая команда', () => {
    expect(neighborsTaken(progress('Б', { А: 'taken', Б: 'not_taken' }))).toBe(true);
  });

  it('взяла только своя команда — не соседи', () => {
    expect(neighborsTaken(progress('А', { А: 'taken', Б: 'not_taken' }))).toBe(false);
  });

  it('никто не взял или плашки нет', () => {
    expect(neighborsTaken(progress('А', { А: 'not_taken', Б: 'no_epic' }))).toBe(false);
    expect(neighborsTaken(null)).toBe(false);
    expect(neighborsTaken(undefined)).toBe(false);
  });
});

describe('teamTakeLine', () => {
  it('у взявшей команды — сценарии с кварталом', () => {
    expect(teamTakeLine({
      team: 'Команда А',
      status: 'taken',
      scenarios: [
        { id: 's1', name: 'План IV', quarter_label: '4 кв. 2026' },
        { id: 's2', name: 'План I', quarter_label: '1 кв. 2027' },
      ],
    })).toBe('Команда А — взят в работу: «План IV», 4 кв. 2026; «План I», 1 кв. 2027');
  });

  it('не взят и нет эпика', () => {
    expect(teamTakeLine({ team: 'Б', status: 'not_taken', scenarios: [] }))
      .toBe('Б — эпик есть, не взят');
    expect(teamTakeLine({ team: 'В', status: 'no_epic', scenarios: [] })).toBe('В — нет эпика');
  });
});

describe('neighborsTakenTitle', () => {
  it('склоняет число задач', () => {
    expect(neighborsTakenTitle(1)).toBe('1 задачу уже взяли соседи, у вас не включена');
    expect(neighborsTakenTitle(3)).toBe('3 задачи уже взяли соседи, у вас не включены');
    expect(neighborsTakenTitle(5)).toBe('5 задач уже взяли соседи, у вас не включены');
    expect(neighborsTakenTitle(11)).toBe('11 задач уже взяли соседи, у вас не включены');
    expect(neighborsTakenTitle(21)).toBe('21 задачу уже взяли соседи, у вас не включена');
  });
});
