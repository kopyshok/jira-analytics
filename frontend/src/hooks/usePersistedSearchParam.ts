import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router';

/**
 * Параметр URL с резервной копией в localStorage. URL имеет приоритет
 * (для deep-link), localStorage используется при возврате на страницу
 * без параметра в URL — чтобы выбор не сбрасывался при переключении.
 */
export function usePersistedSearchParam(
  paramKey: string,
  storageKey: string,
): [string | null, (id: string | null) => void] {
  const [searchParams, setSearchParams] = useSearchParams();
  const fromUrl = searchParams.get(paramKey);

  const [value, setValueState] = useState<string | null>(() => {
    if (fromUrl) return fromUrl;
    if (typeof window === 'undefined') return null;
    return localStorage.getItem(storageKey);
  });

  useEffect(() => {
    if (!fromUrl && value) {
      const next = new URLSearchParams(searchParams);
      next.set(paramKey, value);
      setSearchParams(next, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setValue = (id: string | null) => {
    setValueState(id);
    const next = new URLSearchParams(searchParams);
    if (id) {
      next.set(paramKey, id);
      localStorage.setItem(storageKey, id);
    } else {
      next.delete(paramKey);
      localStorage.removeItem(storageKey);
    }
    setSearchParams(next, { replace: true });
  };

  return [value, setValue];
}
