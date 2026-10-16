import { useNavigate } from 'react-router';
import { useNavSections } from './navConfig';

export function AuroraSidebar() {
  const navigate = useNavigate();
  const { groups, selectedKey } = useNavSections();

  return (
    <div className="glass side">
      <div className="side-logo">
        <svg width="30" height="30" viewBox="0 0 32 32" fill="none">
          <circle cx="16" cy="16" r="13" stroke="var(--accent-1)" strokeWidth="1.5" opacity="0.4" />
          <path d="M5 16a11 11 0 0 1 22 0" stroke="var(--accent-1)" strokeWidth="2.4" strokeLinecap="round" />
          <circle cx="16" cy="5" r="2.6" fill="var(--accent-1)" />
          <circle cx="16" cy="16" r="2.2" fill="var(--accent-2)" />
        </svg>
        <div style={{ lineHeight: 1.1 }}>
          <div className="serif" style={{ fontSize: 17, fontWeight: 600, letterSpacing: '-0.01em' }}>
            Jira
          </div>
          <div
            style={{
              display: 'flex',
              alignItems: 'baseline',
              gap: 6,
              marginTop: 1,
            }}
          >
            <span
              style={{
                fontSize: 9.5,
                textTransform: 'uppercase',
                letterSpacing: '0.18em',
                color: 'var(--accent-1)',
                fontWeight: 600,
              }}
            >
              Analytics
            </span>
            <span
              title={`Версия ${__APP_VERSION__}`}
              style={{
                fontSize: 9,
                color: 'var(--text-muted)',
                fontWeight: 500,
                letterSpacing: '0.04em',
              }}
            >
              v{__APP_VERSION__}
            </span>
          </div>
        </div>
      </div>
      <div className="scroll-y" style={{ flex: 1, margin: '0 -4px', padding: '0 4px' }}>
        {groups.map((g) => (
          <div key={g.label}>
            <div className="side-group">{g.label}</div>
            {g.items.map(({ key, icon: Icon, label }) => (
              <button
                key={key}
                className={`side-item${selectedKey === key ? ' active' : ''}`}
                onClick={() => navigate(key)}
              >
                <span className="side-ico" style={{ display: 'inline-flex' }}>
                  <Icon size={17} strokeWidth={1.8} />
                </span>
                <span
                  style={{
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {label}
                </span>
              </button>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
