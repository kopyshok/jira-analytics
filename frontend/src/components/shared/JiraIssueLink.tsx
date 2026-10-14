import type { AnchorHTMLAttributes } from 'react';
import { useJiraBrowseUrl } from '../../hooks/useSettings';

type Props = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, 'href' | 'target' | 'rel'> & {
  issueKey: string;
};

/** Ссылка на задачу в Jira; пока адрес Jira не задан — просто ключ без ссылки. */
export default function JiraIssueLink({ issueKey, children, style, className, ...rest }: Props) {
  const href = useJiraBrowseUrl()(issueKey);
  if (!href) {
    return <span style={style} className={className}>{children ?? issueKey}</span>;
  }
  return (
    <a href={href} target="_blank" rel="noreferrer" style={style} className={className} {...rest}>
      {children ?? issueKey}
    </a>
  );
}
