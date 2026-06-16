import WidgetShell from './WidgetShell';
import { useDeskWidget } from './useDeskWidget';
import { initials } from './format';
import { deskStatusKind } from './deskStatus';
import type { AvailabilityMember, DeskProject, TeamAvailabilityData } from '../../types/desk';

const DOT_VAR: Record<string, string> = {
  active: 'var(--accent)',
  review: 'var(--amber)',
  done: 'var(--green)',
  returned: 'var(--red)',
  neutral: 'var(--ink-4)',
};

const AV_CLASSES = ['desk-av-1', 'desk-av-2', 'desk-av-3', 'desk-av-4'];

function MemberRow({ m, avIdx }: { m: AvailabilityMember; avIdx: number }) {
  const projects = m.projects.slice(0, 4);
  return (
    <div className="desk-member-row">
      <div className={`desk-member-avatar ${AV_CLASSES[avIdx % AV_CLASSES.length]}`}>
        {initials(m.display_name)}
      </div>
      <div className="desk-member-info">
        <div className="desk-member-name">{m.display_name}</div>
        <div className="desk-member-count">проектов: {m.projects.length}</div>
        <div className="desk-member-projects">
          {projects.map((p: DeskProject, i) => (
            <div className="desk-member-project" key={`${p.key ?? ''}-${i}`}>
              <span className="desk-mpj-dot" style={{ background: DOT_VAR[deskStatusKind(p.status)] }} />
              {p.jira_url ? (
                <a href={p.jira_url} target="_blank" rel="noreferrer" style={{ color: 'inherit' }}>
                  {p.title ?? p.key ?? '—'}
                </a>
              ) : (p.title ?? p.key ?? '—')}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function TeamAvailabilityWidget({ token, title }: { token: string; title: string }) {
  const { data, isLoading, isError } = useDeskWidget<TeamAvailabilityData>(token, 'team_availability');
  const members = (data?.members ?? []).filter((m) => m.projects.length > 0);

  return (
    <WidgetShell
      title={title}
      isLoading={isLoading}
      isError={isError}
      isEmpty={members.length === 0}
      emptyText="Нет занятости команды"
    >
      <div className="desk-team-list">
        {members.map((m, i) => (
          <MemberRow key={m.id} m={m} avIdx={i} />
        ))}
      </div>
    </WidgetShell>
  );
}
