import React from 'react';
import { Tag, Button, Dropdown, App, Space } from 'antd';
import html2canvas from 'html2canvas';
import {
  ReloadOutlined,
  FileImageOutlined,
  MoreOutlined,
} from '@ant-design/icons';
import type { ProjectDetail, ProjectSummary } from '../../types/projects';
import { useRegenerateSummary } from '../../hooks/useProjectSummary';
import { AiGate } from '../shared/AiGate';
import { trackAction } from '../../lib/usage/track';

type ViewMode = 'analysis' | 'presentation';

interface Props {
  detail: ProjectDetail | undefined;
  summary: ProjectSummary | null | undefined;
  view: ViewMode;
  onViewChange: (v: ViewMode) => void;
}

const STATUS_COLOR: Record<string, string> = {
  new: '#7e94b8',
  indeterminate: '#00c9c8',
  done: '#67d68d',
};

function formatDate(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const yyyy = d.getFullYear();
  return `${dd}.${mm}.${yyyy}`;
}

function formatDateTime(iso: string): string {
  const d = new Date(iso);
  const dd = String(d.getDate()).padStart(2, '0');
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const yyyy = d.getFullYear();
  const hh = String(d.getHours()).padStart(2, '0');
  const min = String(d.getMinutes()).padStart(2, '0');
  return `${dd}.${mm}.${yyyy} ${hh}:${min}`;
}

export const ProjectHeader: React.FC<Props> = ({ detail, summary, view, onViewChange }) => {
  const regen = useRegenerateSummary();
  const { message } = App.useApp();
  const [exporting, setExporting] = React.useState(false);

  const handleRegen = () => {
    if (!detail) return;
    const projectKey = detail.key;
    regen.mutate(projectKey, {
      onSuccess: () => trackAction('ai_summary_refreshed', projectKey),
    });
  };

  const handlePng = async () => {
    if (!detail) return;
    onViewChange('presentation');
    setExporting(true);
    try {
      // wait for presentation view + Recharts animations
      await new Promise((r) => setTimeout(r, 800));
      const target = document.querySelector<HTMLElement>('.presentation-view');
      if (!target) {
        message.error('Контейнер для экспорта не найден');
        return;
      }
      const canvas = await html2canvas(target, {
        backgroundColor: '#0d1c33',
        scale: 2,
        useCORS: true,
        height: target.scrollHeight,
        windowHeight: target.scrollHeight,
      });
      const dataUrl = canvas.toDataURL('image/png');
      const a = document.createElement('a');
      const today = new Date();
      const stamp = `${today.getFullYear()}${String(today.getMonth() + 1).padStart(2, '0')}${String(today.getDate()).padStart(2, '0')}`;
      a.href = dataUrl;
      a.download = `${detail.key}_${stamp}.png`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } catch (e) {
      message.error('Не удалось сохранить картинку');
      console.error(e);
    } finally {
      setExporting(false);
    }
  };

  const statusCategory = detail?.status_category ?? 'new';
  const statusColor = STATUS_COLOR[statusCategory] ?? '#7e94b8';

  const moreItems = [
    { key: 'copy-link', label: 'Копировать ссылку' },
  ];

  return (
    <div
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 5,
        background: '#0d1c33',
        padding: '12px 20px',
        borderBottom: '1px solid rgba(255,255,255,0.06)',
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'space-between',
        gap: 12,
      }}
    >
      {/* Left: title + meta */}
      <div style={{ minWidth: 0, flex: 1 }}>
        <div
          style={{
            fontSize: 20,
            fontWeight: 700,
            color: '#fff',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            lineHeight: 1.3,
          }}
        >
          {detail?.summary ?? '—'}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 4, flexWrap: 'wrap' }}>
          {detail?.key && (
            <a
              href={`https://itgri.atlassian.net/browse/${detail.key}`}
              target="_blank"
              rel="noreferrer"
              style={{ color: '#00c9c8', fontSize: 12, textDecoration: 'none' }}
            >
              {detail.key}
            </a>
          )}
          {detail?.key && <span style={{ color: '#7e94b8', fontSize: 12 }}>·</span>}
          {(detail?.period_start || detail?.period_end) && (
            <span style={{ color: '#7e94b8', fontSize: 12 }}>
              {formatDate(detail?.period_start ?? null)} — {formatDate(detail?.period_end ?? null)}
            </span>
          )}
          {detail?.status && (
            <>
              <span style={{ color: '#7e94b8', fontSize: 12 }}>·</span>
              <Tag
                style={{
                  background: 'transparent',
                  border: `1px solid ${statusColor}`,
                  color: statusColor,
                  fontSize: 11,
                  margin: 0,
                  lineHeight: '18px',
                }}
              >
                {detail.status}
              </Tag>
            </>
          )}
        </div>
        {summary?.generated_at && (
          <div style={{ fontSize: 11, color: '#7e94b8', marginTop: 3 }}>
            AI-резюме обновлено {formatDateTime(summary.generated_at)}
          </div>
        )}
      </div>

      {/* Right: controls */}
      <div className="project-header-actions" style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
        <Space.Compact>
          <Button
            size="small"
            type={view === 'analysis' ? 'primary' : 'default'}
            onClick={() => onViewChange('analysis')}
            style={view === 'analysis' ? { background: '#00c9c8', borderColor: '#00c9c8', color: '#0d1c33' } : { color: '#7e94b8' }}
          >
            Анализ
          </Button>
          <Button
            size="small"
            type={view === 'presentation' ? 'primary' : 'default'}
            onClick={() => onViewChange('presentation')}
            style={view === 'presentation' ? { background: '#00c9c8', borderColor: '#00c9c8', color: '#0d1c33' } : { color: '#7e94b8' }}
          >
            Презентация
          </Button>
        </Space.Compact>

        <AiGate>
          <Button
            size="small"
            icon={<ReloadOutlined />}
            loading={regen.isPending}
            onClick={handleRegen}
            disabled={!detail}
            style={{ color: '#7e94b8' }}
          >
            Обновить AI
          </Button>
        </AiGate>

        <Button
          size="small"
          icon={<FileImageOutlined />}
          onClick={handlePng}
          loading={exporting}
          disabled={!detail}
          style={{ color: '#7e94b8' }}
        >
          PNG
        </Button>

        <Dropdown menu={{ items: moreItems }} trigger={['click']}>
          <Button size="small" icon={<MoreOutlined />} style={{ color: '#7e94b8' }} />
        </Dropdown>
      </div>
    </div>
  );
};
