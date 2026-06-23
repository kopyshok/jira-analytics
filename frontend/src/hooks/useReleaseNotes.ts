import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { releaseNotesApi } from '../api/releaseNotes';
import type { ReleaseNoteCreate, ReleaseNoteUpdate } from '../types/releaseNotes';

const KEY_UNREAD = ['release-notes', 'unread'] as const;
const KEY_ALL = ['release-notes', 'all'] as const;
const KEY_DRAFTS = ['release-notes', 'drafts'] as const;

export function useUnreadReleaseNotes() {
  return useQuery({
    queryKey: KEY_UNREAD,
    queryFn: () => releaseNotesApi.getUnread(),
    staleTime: 60_000,
  });
}

export function useAllReleaseNotes() {
  return useQuery({
    queryKey: KEY_ALL,
    queryFn: () => releaseNotesApi.getAll(),
    staleTime: 60_000,
  });
}

export function useMarkSeen() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (version: string) => releaseNotesApi.markSeen(version),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEY_UNREAD });
      qc.invalidateQueries({ queryKey: KEY_ALL });
    },
  });
}

export function useDraftReleaseNotes() {
  return useQuery({
    queryKey: KEY_DRAFTS,
    queryFn: () => releaseNotesApi.listDrafts(),
    staleTime: 30_000,
  });
}

export function useCreateReleaseNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ReleaseNoteCreate) => releaseNotesApi.create(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['release-notes'] }),
  });
}

export function useUpdateReleaseNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ReleaseNoteUpdate }) =>
      releaseNotesApi.update(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['release-notes'] }),
  });
}

export function useDeleteReleaseNote() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => releaseNotesApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['release-notes'] }),
  });
}

export function usePublishReleaseNotes() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (version: string) => releaseNotesApi.publish(version),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['release-notes'] }),
  });
}

export function useReseedReleaseNotes() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => releaseNotesApi.reseed(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['release-notes'] }),
  });
}

export function useDeleteVersion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (version: string) => releaseNotesApi.deleteVersion(version),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['release-notes'] }),
  });
}
