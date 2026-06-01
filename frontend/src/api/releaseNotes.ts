import { api } from './client';
import type {
  ReleaseNote, ReleaseNoteCreate, ReleaseNoteUpdate, UnreadFeed,
} from '../types/releaseNotes';

export const releaseNotesApi = {
  getUnread: () => api.get<UnreadFeed>('/release-notes/unread'),
  getAll: () => api.get<UnreadFeed>('/release-notes/all'),
  markSeen: (version: string) =>
    api.post<void>('/release-notes/mark-seen', { version }),

  // admin
  listDrafts: () => api.get<ReleaseNote[]>('/admin/release-notes/drafts'),
  listVersion: (version: string) =>
    api.get<ReleaseNote[]>(`/admin/release-notes/versions/${version}`),
  create: (body: ReleaseNoteCreate) =>
    api.post<ReleaseNote>('/admin/release-notes', body),
  update: (id: string, body: ReleaseNoteUpdate) =>
    api.patch<ReleaseNote>(`/admin/release-notes/${id}`, body),
  remove: (id: string) =>
    api.del<void>(`/admin/release-notes/${id}`),
  publish: (version: string) =>
    api.post<{ published_count: number; version: string }>(
      '/admin/release-notes/publish', { version }
    ),
  deleteVersion: (version: string) =>
    api.del<void>(`/admin/release-notes/version/${version}`),
};
