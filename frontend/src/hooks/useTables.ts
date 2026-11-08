import { useCallback, useEffect, useState } from "react";
import { api } from "../api/client";
import type { TableInfo } from "../types/api";

export function useTables() {
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const res = await api.listTables();
      setTables(res.tables);
    } catch {
      // silently ignore — backend may not be running
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const drop = useCallback(
    async (name: string) => {
      await api.dropTable(name);
      await refresh();
    },
    [refresh]
  );

  return { tables, loading, refresh, drop };
}
