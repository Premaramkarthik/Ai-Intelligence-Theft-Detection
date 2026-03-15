'use client';

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Calendar,
  Camera as CameraIcon,
  Download,
  ExternalLink,
  Filter,
  Search,
  ShieldAlert,
  Trash2,
} from 'lucide-react';

import DashboardShell from '@/components/layout/DashboardShell';
import { authHeaders, buildApiUrl, withApiCredentials } from '@/lib/api';
import { isAuthFailure } from '@/lib/auth';
import { cn } from '@/lib/cn';
import { useAuthStore } from '@/stores/useAuthStore';
import type { HistoryEvent, ReviewStatus } from '@/types/contracts';

export default function HistoryPage() {
  const token = useAuthStore((state) => state.token);
  const logout = useAuthStore((state) => state.logout);
  const queryClient = useQueryClient();
  const [searchTerm, setSearchTerm] = useState('');
  const [filterLabel, setFilterLabel] = useState('all');
  const [storeFilter, setStoreFilter] = useState('all');

  const reviewMutation = useMutation({
    mutationFn: async ({ eventId, reviewStatus }: { eventId: string; reviewStatus: ReviewStatus }) => {
      const response = await fetch(buildApiUrl(`/api/events/${eventId}/review`), {
        ...withApiCredentials(),
        method: 'PATCH',
        headers: {
          ...Object.fromEntries(authHeaders({ token }).entries()),
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ review_status: reviewStatus }),
      });
      if (!response.ok) {
        throw new Error('Failed to update review status');
      }
      return response.json();
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['history-events', token] });
    },
  });

  const { data: events, isLoading } = useQuery<HistoryEvent[]>({
    queryKey: ['history-events', token],
    enabled: Boolean(token),
    queryFn: async () => {
      const response = await fetch(buildApiUrl('/api/events'), {
        ...withApiCredentials(),
        headers: authHeaders({ token }),
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => ({}))) as { detail?: string };
        if (isAuthFailure(response.status, body.detail)) {
          logout();
          return [];
        }
        throw new Error('Failed to fetch historical events');
      }
      return response.json();
    },
  });

  const filteredEvents = events?.filter((event) => {
    const matchesSearch =
      event.camera_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
      event.label.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesFilter = filterLabel === 'all' || event.label === filterLabel;
    const matchesStore = storeFilter === 'all' || event.store_id === storeFilter;
    return matchesSearch && matchesFilter && matchesStore;
  });
  const stores = Array.from(new Set((events ?? []).map((event) => event.store_id)));

  return (
    <DashboardShell>
      <div className="flex flex-col gap-8">
        <div className="flex items-end justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-white">Forensic History</h1>
            <p className="mt-1 text-slate-500">Canonical incident events persisted by the backend pipeline.</p>
          </div>

          <button className="flex items-center gap-2 rounded-xl bg-slate-800 px-4 py-2 text-sm font-semibold text-slate-200 transition-all hover:bg-slate-700">
            <Download className="h-4 w-4" />
            Export CSV
          </button>
        </div>

        <div className="flex flex-wrap items-center gap-4 rounded-2xl border border-slate-800 bg-slate-900/50 p-4">
          <div className="relative min-w-[300px] flex-1">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
            <input
              type="text"
              placeholder="Search by camera or label..."
              value={searchTerm}
              onChange={(event) => setSearchTerm(event.target.value)}
              className="w-full rounded-xl border border-slate-800 bg-slate-950 py-2 pl-10 pr-4 text-sm text-slate-200 transition-all focus:border-blue-500/50 focus:outline-none"
            />
          </div>

          <div className="flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-950 px-3 py-2">
            <Filter className="h-4 w-4 text-slate-500" />
            <select
              value={filterLabel}
              onChange={(event) => setFilterLabel(event.target.value)}
              className="cursor-pointer bg-transparent text-sm text-slate-300 focus:outline-none"
            >
              <option value="all">All Incidents</option>
              <option value="shoplifting">Shoplifting</option>
              <option value="weapon">Weapon</option>
            </select>
          </div>
          <div className="flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-950 px-3 py-2">
            <Filter className="h-4 w-4 text-slate-500" />
            <select
              value={storeFilter}
              onChange={(event) => setStoreFilter(event.target.value)}
              className="cursor-pointer bg-transparent text-sm text-slate-300 focus:outline-none"
            >
              <option value="all">All Stores</option>
              {stores.map((storeId) => (
                <option key={storeId} value={storeId}>
                  {storeId}
                </option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-950 px-3 py-2 text-sm text-slate-400">
            <Calendar className="h-4 w-4 text-slate-500" />
            Latest persisted records
          </div>
        </div>

        <div className="overflow-hidden rounded-3xl border border-slate-800 bg-slate-900 shadow-xl">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-950/50 text-[10px] font-bold uppercase tracking-widest text-slate-500">
                <th className="px-6 py-4">Event Time</th>
                <th className="px-6 py-4">Evidence</th>
                <th className="px-6 py-4">Source</th>
                <th className="px-6 py-4">Detection</th>
                <th className="px-6 py-4">Confidence</th>
                <th className="px-6 py-4">Severity</th>
                <th className="px-6 py-4">Review</th>
                <th className="px-6 py-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/50">
              {isLoading ? <SkeletonRows /> : filteredEvents?.length ? filteredEvents.map((event) => <EventRow key={event.event_id} event={event} onReviewChange={(reviewStatus) => reviewMutation.mutate({ eventId: event.event_id, reviewStatus })} />) : (
                <tr>
                  <td colSpan={8} className="px-6 py-12 text-center text-sm text-slate-500">
                    No persisted incident events match the current filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </DashboardShell>
  );
}

function EventRow({ event, onReviewChange }: { event: HistoryEvent; onReviewChange: (reviewStatus: ReviewStatus) => void }) {
  const date = new Date(event.timestamp);
  const isCritical = event.severity === 'high' || event.severity === 'critical';

  return (
    <tr className="group transition-colors hover:bg-slate-800/20">
      <td className="px-6 py-4">
        <div className="flex flex-col">
          <span className="text-sm font-medium text-slate-200" suppressHydrationWarning>
            {date.toLocaleTimeString()}
          </span>
          <span className="text-[10px] text-slate-500" suppressHydrationWarning>
            {date.toLocaleDateString()}
          </span>
        </div>
      </td>
      <td className="px-6 py-4">
        {event.thumbnail_uri ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={buildApiUrl(`/api/events/${event.event_id}/thumbnail`)}
            alt={event.label}
            className="h-14 w-24 rounded-lg object-cover"
          />
        ) : (
          <div className="h-14 w-24 rounded-lg bg-slate-800" />
        )}
      </td>
      <td className="px-6 py-4">
        <div className="flex items-center gap-2 text-slate-300">
          <CameraIcon className="h-4 w-4 text-slate-600" />
          <div className="flex flex-col">
            <span className="text-sm font-medium">{event.camera_id}</span>
            <span className="text-[10px] text-slate-500">{event.store_id}</span>
          </div>
        </div>
      </td>
      <td className="px-6 py-4">
        <div
          className={cn(
            'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider',
            isCritical ? 'border-red-500/20 bg-red-500/10 text-red-500' : 'border-blue-500/20 bg-blue-500/10 text-blue-400',
          )}
        >
          {isCritical ? <ShieldAlert className="h-3.5 w-3.5" /> : null}
          {event.label}
        </div>
      </td>
      <td className="px-6 py-4">
        <div className="w-24 space-y-1">
          <div className="flex justify-between text-[10px] font-bold text-slate-500">
            <span>MATCH</span>
            <span>{Math.round(event.confidence * 100)}%</span>
          </div>
          <div className="h-1 w-full overflow-hidden rounded-full bg-slate-800">
            <div className={cn('h-full', event.confidence > 0.8 ? 'bg-emerald-500' : 'bg-blue-500')} style={{ width: `${event.confidence * 100}%` }} />
          </div>
        </div>
      </td>
      <td className="px-6 py-4">
        <span className={cn('inline-flex items-center gap-1.5 text-xs font-semibold', isCritical ? 'text-red-400' : 'text-amber-300')}>
          <div className={cn('h-1.5 w-1.5 rounded-full', isCritical ? 'bg-red-400' : 'bg-amber-300')} />
          {event.severity}
        </span>
      </td>
      <td className="px-6 py-4">
        <select
          value={event.review_status}
          onChange={(evt) => onReviewChange(evt.target.value as ReviewStatus)}
          className="rounded-lg border border-slate-800 bg-slate-950 px-2 py-1 text-xs text-slate-300"
        >
          <option value="unreviewed">Unreviewed</option>
          <option value="confirmed">Confirmed</option>
          <option value="false_positive">False Positive</option>
          <option value="needs_review">Needs Review</option>
        </select>
      </td>
      <td className="px-6 py-4 text-right">
        <div className="flex justify-end gap-2 opacity-0 transition-opacity group-hover:opacity-100">
          <a
            href={buildApiUrl(`/api/events/${event.event_id}/evidence`)}
            target="_blank"
            rel="noreferrer"
            className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-slate-800 hover:text-white"
            title="View Evidence"
          >
            <ExternalLink className="h-4 w-4" />
          </a>
          <button className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-red-500/10 hover:text-red-500" title="Delete Log">
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </td>
    </tr>
  );
}

function SkeletonRows() {
  return (
    <>
      {[1, 2, 3, 4, 5].map((value) => (
        <tr key={value}>
          <td colSpan={8} className="px-6 py-6 font-medium">
            <div className="h-4 w-full animate-pulse rounded bg-slate-800" />
          </td>
        </tr>
      ))}
    </>
  );
}
