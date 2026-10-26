/** Route + desk state, both derived from the URL hash so any view is shareable.

 *  `#/desk?d=2026-01-14&ch=9&cm=30&asof=2026-01-14T09:30:00Z`
 *
 *  Keeping this in the URL (rather than component state) means a trader can
 *  paste "the 14th, as seen at the gate" into a chat and the reviewer sees
 *  exactly the same screen - which matters for a product whose whole point is
 *  point-in-time correctness.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { Meta } from "@/api/types";
import { addDays } from "@/lib/format";

export type RouteName = "desk" | "accuracy" | "procurement" | "method";

const ROUTES: RouteName[] = ["desk", "accuracy", "procurement", "method"];

interface HashState {
  route: RouteName;
  params: URLSearchParams;
}

function parseHash(hash: string): HashState {
  const raw = hash.replace(/^#\/?/, "");
  const [path, query] = raw.split("?");
  const candidate = (path || "desk") as RouteName;
  return {
    route: ROUTES.includes(candidate) ? candidate : "desk",
    params: new URLSearchParams(query ?? ""),
  };
}

function buildHash(route: RouteName, params: URLSearchParams): string {
  const query = params.toString();
  return `#/${route}${query ? `?${query}` : ""}`;
}

export interface AppContextValue {
  route: RouteName;
  navigate: (route: RouteName) => void;
  meta: Meta;
  pilotDays: string[];
  deliveryDate: string;
  setDeliveryDate: (value: string) => void;
  cutoff: { hour: number; minute: number };
  setCutoff: (hour: number, minute: number) => void;
  asOf: string | null;
  setAsOf: (value: string | null) => void;
  isLatest: boolean;
}

const AppContext = createContext<AppContextValue | null>(null);

export function AppProvider({ meta, children }: { meta: Meta; children: ReactNode }) {
  const [state, setState] = useState<HashState>(() => parseHash(window.location.hash));

  useEffect(() => {
    const onChange = () => setState(parseHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    if (!window.location.hash) {
      window.history.replaceState(null, "", buildHash("desk", new URLSearchParams()));
    }
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  const pilotDays = useMemo(() => {
    const days: string[] = [];
    let cursor = meta.pilot.start;
    while (cursor <= meta.pilot.end && days.length < 400) {
      days.push(cursor);
      cursor = addDays(cursor, 1);
    }
    return days;
  }, [meta.pilot.start, meta.pilot.end]);

  const update = useCallback(
    (mutate: (params: URLSearchParams) => void) => {
      const next = new URLSearchParams(state.params);
      mutate(next);
      const hash = buildHash(state.route, next);
      if (hash !== window.location.hash) {
        window.location.hash = hash;
      } else {
        setState(parseHash(hash));
      }
    },
    [state.params, state.route],
  );

  const navigate = useCallback(
    (route: RouteName) => {
      window.location.hash = buildHash(route, state.params);
      window.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
    },
    [state.params],
  );

  const rawDate = state.params.get("d");
  const deliveryDate =
    rawDate && pilotDays.includes(rawDate) ? rawDate : (pilotDays.at(-1) ?? meta.pilot.end);

  const cutoff = {
    hour: Number(state.params.get("ch") ?? meta.defaults.cutoff_hour),
    minute: Number(state.params.get("cm") ?? meta.defaults.cutoff_minute),
  };

  const rawAsOf = state.params.get("asof");
  const asOf = rawAsOf && rawAsOf.length > 10 ? rawAsOf : null;

  const value: AppContextValue = {
    route: state.route,
    navigate,
    meta,
    pilotDays,
    deliveryDate,
    setDeliveryDate: (next) => update((params) => params.set("d", next)),
    cutoff,
    setCutoff: (hour, minute) =>
      update((params) => {
        params.set("ch", String(hour));
        params.set("cm", String(minute));
      }),
    asOf,
    setAsOf: (next) =>
      update((params) => {
        if (next) params.set("asof", next);
        else params.delete("asof");
      }),
    isLatest: asOf === null,
  };

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp(): AppContextValue {
  const context = useContext(AppContext);
  if (!context) throw new Error("useApp must be used inside <AppProvider>");
  return context;
}
