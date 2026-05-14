import { useMemo, type ReactNode } from 'react';
import { Drawer, Typography } from 'antd';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { DARK_THEME } from '../../utils/constants';

interface Props {
  open: boolean;
  onClose: () => void;
  title: string;
  /** Raw markdown content. Import via `?raw` from docs/help/*.md */
  content: string;
  /** Base URL for relative image paths inside markdown. Default: /docs/help/ */
  imageBase?: string;
}

/**
 * Right-side справочный drawer. Рендерит markdown из docs/help/, поддерживает
 * GFM таблицы. Картинки разрешаются относительно imageBase.
 */
export default function HelpDrawer({ open, onClose, title, content, imageBase = '/docs/help/' }: Props) {
  const components = useMemo(() => ({
    h1: ({ children }: { children?: ReactNode }) => (
      <Typography.Title level={2} style={{ marginTop: 0, color: DARK_THEME.cyanPrimary }}>
        {children}
      </Typography.Title>
    ),
    h2: ({ children }: { children?: ReactNode }) => (
      <Typography.Title level={3} style={{ marginTop: 28, color: DARK_THEME.cyanPrimary }}>
        {children}
      </Typography.Title>
    ),
    h3: ({ children }: { children?: ReactNode }) => (
      <Typography.Title level={4} style={{ marginTop: 22 }}>
        {children}
      </Typography.Title>
    ),
    h4: ({ children }: { children?: ReactNode }) => (
      <Typography.Title level={5} style={{ marginTop: 18 }}>
        {children}
      </Typography.Title>
    ),
    table: ({ children }: { children?: ReactNode }) => (
      <div className="help-table-wrap">
        <table className="help-table">{children}</table>
      </div>
    ),
    img: (props: { src?: string; alt?: string }) => {
      const src = props.src && !/^https?:|^\//.test(props.src)
        ? imageBase + props.src.replace(/^\.\//, '')
        : props.src;
      return (
        <img
          src={src}
          alt={props.alt}
          title={props.alt}
          style={{
            display: 'block',
            maxWidth: '100%',
            borderRadius: 6,
            border: `1px solid ${DARK_THEME.border}`,
            margin: '12px 0 6px 0',
          }}
        />
      );
    },
    p: ({ children }: { children?: ReactNode }) => {
      // Avoid <p> wrapping a block-level img — yields invalid DOM.
      // Detect single-child img and unwrap. Otherwise normal paragraph.
      const arr = Array.isArray(children) ? children : [children];
      const first = arr.find(c => c !== null && c !== undefined && c !== '');
      if (
        arr.filter(c => c !== null && c !== undefined && c !== '' && !(typeof c === 'string' && c.trim() === '')).length === 1
        && first
        && typeof first === 'object'
        && 'type' in (first as object)
        && (first as { type?: unknown }).type === 'img'
      ) {
        return <>{children}</>;
      }
      return <p>{children}</p>;
    },
    code: ({ children, className }: { children?: ReactNode; className?: string }) => {
      const isBlock = className?.startsWith('language-');
      if (isBlock) {
        return <pre className="help-code-block"><code>{children}</code></pre>;
      }
      return <code className="help-code-inline">{children}</code>;
    },
    a: ({ href, children }: { href?: string; children?: ReactNode }) => (
      <Typography.Link href={href} target={href?.startsWith('http') ? '_blank' : undefined} rel="noreferrer">
        {children}
      </Typography.Link>
    ),
  }), [imageBase]);

  return (
    <Drawer
      title={title}
      open={open}
      onClose={onClose}
      width="min(960px, 70vw)"
      placement="right"
      destroyOnClose
      styles={{
        body: { padding: '20px 28px', background: DARK_THEME.cardBg },
        header: { background: DARK_THEME.cardBg, borderBottom: `1px solid ${DARK_THEME.border}` },
      }}
    >
      <div className="help-markdown">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
          {content}
        </ReactMarkdown>
      </div>
    </Drawer>
  );
}
