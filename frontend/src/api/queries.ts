/** Server-state hooks. TanStack Query owns caching, retries and background refresh;
 *  nothing in the UI reaches for fetch directly. */

import { useQuery } from "@tanstack/react-query";
import { request, toQuery } from "./client";
import type {
  AccuracyReport,
  Decision,
  DeliveryDays,
  Meta,
  ProcurementPlan,
  VintageEvolution,
} from "./types";

export interface Cutoff {
  hour: number;
  minute: number;
}

export const queryKeys = {
  meta: ["meta"] as const,
  days: (asOf: string | null, cutoff: Cutoff) =>
    ["days", asOf, cutoff.hour, cutoff.minute] as const,
  decision: (date: string, cutoff: Cutoff, asOf: string | null) =>
    ["decision", date, cutoff.hour, cutoff.minute, asOf] as const,
  vintages: (date: string, cutoff: Cutoff, asOf: string | null) =>
    ["vintages", date, cutoff.hour, cutoff.minute, asOf] as const,
  accuracy: (start: string | null, end: string | null, cutoff: Cutoff, asOf: string | null) =>
    ["accuracy", start, end, cutoff.hour, cutoff.minute, asOf] as const,
  plan: (body: string) => ["plan", body] as const,
};

export function useMeta() {
  return useQuery({
    queryKey: queryKeys.meta,
    queryFn: () => request<Meta>("/api/v1/meta"),
    staleTime: 60_000,
  });
}

export function useDeliveryDays(asOf: string | null, cutoff: Cutoff) {
  return useQuery({
    queryKey: queryKeys.days(asOf, cutoff),
    queryFn: () =>
      request<DeliveryDays>(
        `/api/v1/delivery-days${toQuery({
          as_of: asOf,
          cutoff_hour: cutoff.hour,
          cutoff_minute: cutoff.minute,
        })}`,
      ),
    staleTime: 30_000,
  });
}

export function useDecision(date: string, cutoff: Cutoff, asOf: string | null) {
  return useQuery({
    queryKey: queryKeys.decision(date, cutoff, asOf),
    queryFn: () =>
      request<Decision>(
        `/api/v1/decision/${date}${toQuery({
          as_of: asOf,
          cutoff_hour: cutoff.hour,
          cutoff_minute: cutoff.minute,
        })}`,
      ),
    staleTime: 30_000,
  });
}

export function useVintages(date: string, cutoff: Cutoff, asOf: string | null, enabled = true) {
  return useQuery({
    queryKey: queryKeys.vintages(date, cutoff, asOf),
    queryFn: () =>
      request<VintageEvolution>(
        `/api/v1/decision/${date}/vintages${toQuery({
          as_of: asOf,
          cutoff_hour: cutoff.hour,
          cutoff_minute: cutoff.minute,
          limit: 18,
        })}`,
      ),
    enabled,
    staleTime: 30_000,
  });
}

export function useAccuracy(
  start: string | null,
  end: string | null,
  cutoff: Cutoff,
  asOf: string | null,
) {
  return useQuery({
    queryKey: queryKeys.accuracy(start, end, cutoff, asOf),
    queryFn: () =>
      request<AccuracyReport>(
        `/api/v1/accuracy/report${toQuery({
          start,
          end,
          as_of: asOf,
          cutoff_hour: cutoff.hour,
          cutoff_minute: cutoff.minute,
        })}`,
      ),
    staleTime: 30_000,
  });
}

export interface PlanRequest {
  delivery_date: string;
  as_of: string | null;
  cutoff_hour: number;
  cutoff_minute: number;
  demand_profile: string;
  peak_mw: number;
  trough_mw: number;
  flat_mw: number;
  c_short: number;
  c_long: number;
}

export function usePlan(body: PlanRequest) {
  const serialised = JSON.stringify(body);
  return useQuery({
    queryKey: queryKeys.plan(serialised),
    queryFn: () =>
      request<ProcurementPlan>("/api/v1/procurement/plan", {
        method: "POST",
        body: serialised,
      }),
    staleTime: 30_000,
  });
}

export function exportCsvUrl(cutoff: Cutoff, asOf: string | null): string {
  return `/api/v1/accuracy/export.csv${toQuery({
    as_of: asOf,
    cutoff_hour: cutoff.hour,
    cutoff_minute: cutoff.minute,
  })}`;
}
