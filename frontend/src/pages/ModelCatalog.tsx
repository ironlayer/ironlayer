import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { ChevronLeft, ChevronRight, Database, Filter, Search } from 'lucide-react';
import { useModels } from '../hooks/useModels';
import type { ModelInfo, ModelKind } from '../api/types';
import { formatDate, formatDateRange, statusColor } from '../utils/formatting';

/* ------------------------------------------------------------------ */
/* Kind badge colors                                                   */
/* ------------------------------------------------------------------ */

const KIND_COLORS: Record<ModelKind, string> = {
  FULL_REFRESH: 'bg-purple-50 text-purple-700',
  INCREMENTAL_BY_TIME_RANGE: 'bg-blue-50 text-blue-700',
  APPEND_ONLY: 'bg-teal-50 text-teal-700',
  MERGE_BY_KEY: 'bg-orange-50 text-orange-700',
};

/* ------------------------------------------------------------------ */
/* Model card                                                          */
/* ------------------------------------------------------------------ */

function ModelCard({ model }: { model: ModelInfo }) {
  return (
    <Link
      to={`/models/${encodeURIComponent(model.model_name)}`}
      className="group rounded-lg border border-gray-200 bg-white p-4 transition-shadow hover:shadow-md"
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-2">
          <Database size={16} className="text-ironlayer-500" />
          <h3 className="text-sm font-semibold text-gray-900 group-hover:text-ironlayer-600">
            {model.model_name}
          </h3>
        </div>
        {model.last_run_status && (
          <span
            className={`inline-flex rounded-full px-1.5 py-0.5 text-[10px] font-medium ${statusColor(
              model.last_run_status,
            )}`}
          >
            {model.last_run_status}
          </span>
        )}
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5">
        <span
          className={`inline-flex rounded px-1.5 py-0.5 text-[10px] font-medium ${
            KIND_COLORS[model.kind] ?? 'bg-gray-50 text-gray-600'
          }`}
        >
          {model.kind.replace(/_/g, ' ')}
        </span>
        <span className="inline-flex rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-600">
          {model.materialization}
        </span>
        {model.tags.slice(0, 3).map((tag) => (
          <span
            key={tag}
            className="inline-flex rounded bg-gray-50 px-1.5 py-0.5 text-[10px] text-gray-500"
          >
            {tag}
          </span>
        ))}
      </div>

      <div className="mt-3 flex items-center justify-between text-xs text-gray-500">
        {model.owner && <span>Owner: {model.owner}</span>}
        {model.watermark_range && (
          <span>WM: {formatDateRange(model.watermark_range)}</span>
        )}
      </div>

      <p className="mt-1 text-[11px] text-gray-400">
        Updated {formatDate(model.last_modified_at)}
      </p>
    </Link>
  );
}

/* ------------------------------------------------------------------ */
/* Page component                                                      */
/* ------------------------------------------------------------------ */

const PAGE_SIZE = 24;

function ModelCatalog() {
  const [searchQuery, setSearchQuery] = useState('');
  const [kindFilter, setKindFilter] = useState<ModelKind | ''>('');
  const [ownerFilter, setOwnerFilter] = useState('');
  const [tagFilter, setTagFilter] = useState('');
  const [showFilters, setShowFilters] = useState(false);
  const [page, setPage] = useState(0);

  const { models, loading, error } = useModels({
    kind: kindFilter || undefined,
    owner: ownerFilter || undefined,
    tag: tagFilter || undefined,
    search: searchQuery || undefined,
  });

  // Derive unique owners and tags for filter dropdowns
  const { owners, tags } = useMemo(() => {
    const ownerSet = new Set<string>();
    const tagSet = new Set<string>();
    for (const m of models) {
      if (m.owner) ownerSet.add(m.owner);
      for (const t of m.tags) tagSet.add(t);
    }
    return {
      owners: Array.from(ownerSet).sort(),
      tags: Array.from(tagSet).sort(),
    };
  }, [models]);

  // Client-side search filtering (augments server-side filtering)
  const filtered = useMemo(() => {
    if (!searchQuery.trim()) return models;
    const q = searchQuery.toLowerCase();
    return models.filter(
      (m) =>
        m.model_name.toLowerCase().includes(q) ||
        (m.owner ?? '').toLowerCase().includes(q) ||
        m.tags.some((t) => t.toLowerCase().includes(q)),
    );
  }, [models, searchQuery]);

  // Reset page when filters change.
  useEffect(() => {
    setPage(0);
  }, [searchQuery, kindFilter, ownerFilter, tagFilter]);

  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
  const paginatedModels = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const showingFrom = filtered.length === 0 ? 0 : page * PAGE_SIZE + 1;
  const showingTo = Math.min((page + 1) * PAGE_SIZE, filtered.length);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Model Catalog</h1>
        <p className="mt-1 text-sm text-gray-500">
          Browse and inspect all registered data models.
        </p>
      </div>

      {/* Search & filters */}
      <div className="space-y-3">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <Search
              size={16}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400"
            />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search models by name, owner, or tag..."
              aria-label="Search models"
              className="w-full rounded-lg border border-gray-300 py-2 pl-9 pr-3 text-sm focus:border-ironlayer-400 focus:outline-none focus:ring-1 focus:ring-ironlayer-400"
            />
          </div>
          <button
            onClick={() => setShowFilters((prev) => !prev)}
            aria-expanded={showFilters}
            aria-label="Toggle model filters"
            className={`flex items-center gap-1.5 rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${
              showFilters
                ? 'border-ironlayer-300 bg-ironlayer-50 text-ironlayer-700'
                : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
            }`}
          >
            <Filter size={14} aria-hidden="true" />
            Filters
          </button>
        </div>

        {showFilters && (
          <div className="flex gap-3 rounded-lg border border-gray-200 bg-white p-3">
            <div className="flex-1">
              <label className="mb-1 block text-xs font-medium text-gray-600">
                Kind
              </label>
              <select
                value={kindFilter}
                onChange={(e) => setKindFilter(e.target.value as ModelKind | '')}
                className="w-full rounded-lg border border-gray-300 px-2 py-1.5 text-sm focus:border-ironlayer-400 focus:outline-none focus:ring-1 focus:ring-ironlayer-400"
              >
                <option value="">All</option>
                <option value="FULL_REFRESH">Full Refresh</option>
                <option value="INCREMENTAL_BY_TIME_RANGE">Incremental</option>
                <option value="APPEND_ONLY">Append Only</option>
                <option value="MERGE_BY_KEY">Merge by Key</option>
              </select>
            </div>
            <div className="flex-1">
              <label className="mb-1 block text-xs font-medium text-gray-600">
                Owner
              </label>
              <select
                value={ownerFilter}
                onChange={(e) => setOwnerFilter(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-2 py-1.5 text-sm focus:border-ironlayer-400 focus:outline-none focus:ring-1 focus:ring-ironlayer-400"
              >
                <option value="">All</option>
                {owners.map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex-1">
              <label className="mb-1 block text-xs font-medium text-gray-600">
                Tag
              </label>
              <select
                value={tagFilter}
                onChange={(e) => setTagFilter(e.target.value)}
                className="w-full rounded-lg border border-gray-300 px-2 py-1.5 text-sm focus:border-ironlayer-400 focus:outline-none focus:ring-1 focus:ring-ironlayer-400"
              >
                <option value="">All</option>
                {tags.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
          </div>
        )}
      </div>

      {/* Results */}
      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-ironlayer-600 border-t-transparent" role="status" aria-label="Loading models" />
        </div>
      ) : error ? (
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-center text-sm text-red-700">
          {error}
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-lg border border-gray-200 bg-white p-8 text-center text-sm text-gray-500">
          No models found matching your criteria.
        </div>
      ) : (
        <>
          <div className="grid grid-cols-3 gap-4">
            {paginatedModels.map((m) => (
              <ModelCard key={m.model_name} model={m} />
            ))}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className="flex items-center justify-between border-t border-gray-200 pt-4">
              <p className="text-sm text-gray-500">
                Showing {showingFrom}-{showingTo} of {filtered.length} models
              </p>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(0, p - 1))}
                  disabled={page === 0}
                  aria-label="Go to previous page"
                  className="flex items-center gap-1 rounded-lg border border-gray-200 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <ChevronLeft size={14} aria-hidden="true" />
                  Previous
                </button>
                <span className="text-sm text-gray-500">
                  Page {page + 1} of {totalPages}
                </span>
                <button
                  onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
                  disabled={page >= totalPages - 1}
                  aria-label="Go to next page"
                  className="flex items-center gap-1 rounded-lg border border-gray-200 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  Next
                  <ChevronRight size={14} aria-hidden="true" />
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}

export default ModelCatalog;
