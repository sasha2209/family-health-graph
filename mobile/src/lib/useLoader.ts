import { useFocusEffect } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';

import { ApiError } from './api';
import { useSession } from './session';

/** Load data when a screen comes into focus, with pull-to-refresh support. */
export function useLoader<T>(load: () => Promise<T>) {
  const { signOut } = useSession();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const loadRef = useRef(load);
  useEffect(() => { loadRef.current = load; });

  const run = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true);
    try {
      setData(await loadRef.current());
      setError(null);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) {
        await signOut({ revoke: false }); // session expired, revoked, or the account was deleted
        return;
      }
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshing(false);
    }
  }, [signOut]);

  useFocusEffect(useCallback(() => { run(); }, [run]));

  return { data, error, refreshing, reload: () => run(true), setData };
}
