import { api, BASE_URL } from './client';

export type FeedbackKind = 'bug' | 'idea';

export interface AttachmentRef {
  filename: string;
  mime: string;
  size: number;
  path: string;
}

export interface FeedbackAuthor {
  id: string;
  display_name: string;
  email: string;
}

export interface FeedbackItem {
  id: string;
  kind: FeedbackKind;
  author: FeedbackAuthor;
  title: string;
  body: string;
  page_url: string | null;
  read_at: string | null;
  read_by: string | null;
  steps_to_reproduce: string | null;
  expected: string | null;
  actual: string | null;
  context: Record<string, unknown> | null;
  attachments: AttachmentRef[];
  created_at: string;
  updated_at: string;
}

export interface BugCreatePayload {
  title: string;
  body: string;
  page_url?: string;
  steps_to_reproduce?: string;
  expected?: string;
  actual?: string;
  context?: Record<string, unknown>;
  attachments?: AttachmentRef[];
}

export interface IdeaCreatePayload {
  title: string;
  body: string;
  page_url?: string;
}

export const feedbackApi = {
  createBug: (p: BugCreatePayload) => api.post<FeedbackItem>('/feedback/bugs', p),
  createIdea: (p: IdeaCreatePayload) => api.post<FeedbackItem>('/feedback/ideas', p),
  my: () => api.get<FeedbackItem[]>('/feedback/my'),
  ideasFeed: () => api.get<FeedbackItem[]>('/feedback/ideas', { scope: 'all' }),
  adminListBugs: (filter: 'unread' | 'all' | 'read' = 'unread') =>
    api.get<FeedbackItem[]>('/feedback/admin/bugs', { filter }),
  adminListIdeas: (filter: 'unread' | 'all' | 'read' = 'unread') =>
    api.get<FeedbackItem[]>('/feedback/admin/ideas', { filter }),
  markRead: (ids: string[]) => api.post<void>('/feedback/admin/mark-read', { ids }),
  markUnread: (ids: string[]) => api.post<void>('/feedback/admin/mark-unread', { ids }),
  uploadAttachment: async (file: File): Promise<AttachmentRef> => {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch(`${BASE_URL}/feedback/attachments`, {
      method: 'POST',
      body: form,
      credentials: 'include',
    });
    if (!res.ok) throw new Error(`Upload failed: ${res.status}`);
    return (await res.json()) as AttachmentRef;
  },
  exportUrl: (): string => `${BASE_URL}/feedback/admin/export`,
};
