import { useCallback, useState } from "react";
import { api } from "../api/client";
import type { QueryResult } from "../types/api";

interface QueryState {
  result: QueryResult | null;
  error: string | null;
  loading: boolean;
}

export function useQuery() {
  const [state, setState] = useState<QueryState>({
    result: null,
    error: null,
    loading: false,
  });

  const execute = useCallback(async (sql: string): Promise<QueryResult | null> => {
    const trimmed = sql.trim();
    if (!trimmed) return null;

    setState({ result: null, error: null, loading: true });
    try {
      const result = await api.executeQuery(trimmed);
      setState({ result, error: null, loading: false });
      return result;
    } catch (err) {
      setState({
        result: null,
        error: err instanceof Error ? err.message : String(err),
        loading: false,
      });
      return null;
    }
  }, []);

  return { ...state, execute };
}
