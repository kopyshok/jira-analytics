export type ReleaseNoteType = 'new' | 'improvement' | 'fix';

export type ReleaseSection =
  | 'scenarios' | 'resources' | 'analytics' | 'issues'
  | 'dashboard' | 'backlog' | 'sync' | 'settings' | 'general';

export interface ReleaseNote {
  id: string;
  version: string | null;
  note_type: ReleaseNoteType;
  section: ReleaseSection;
  title: string;
  description: string;
  help_link: string | null;
  is_hidden: boolean;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

export interface VersionFeed {
  version: string;
  notes: ReleaseNote[];
}

export interface UnreadFeed {
  unread_versions: string[];
  feeds: VersionFeed[];
}

export interface ReleaseNoteCreate {
  note_type: ReleaseNoteType;
  section: ReleaseSection;
  title: string;
  description: string;
  help_link?: string | null;
}

export interface ReleaseNoteUpdate {
  note_type?: ReleaseNoteType;
  section?: ReleaseSection;
  title?: string;
  description?: string;
  help_link?: string | null;
  is_hidden?: boolean;
  sort_order?: number;
}

export const NOTE_TYPE_LABELS: Record<ReleaseNoteType, string> = {
  new: 'Новое',
  improvement: 'Улучшение',
  fix: 'Исправление',
};

export const NOTE_TYPE_COLORS: Record<ReleaseNoteType, string> = {
  new: '#52c41a',
  improvement: '#1677ff',
  fix: '#8c8c8c',
};

export const SECTION_LABELS: Record<ReleaseSection, string> = {
  scenarios: 'Сценарии',
  resources: 'Ресурсы',
  analytics: 'Аналитика',
  issues: 'Анализ задач',
  dashboard: 'Дашборд',
  backlog: 'Бэклог',
  sync: 'Синхронизация',
  settings: 'Настройки',
  general: 'Общее',
};
