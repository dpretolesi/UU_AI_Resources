/* ============================================================
   AI Research Hub — Main Application Script
   Handles: data loading, search (Pagefind + fallback), filters,
   sorting, URL sync, dark mode, submit modal, and all UI state.
   ============================================================ */

(function () {
  'use strict';

  // ─── Configuration ──────────────────────────────────────────
  const DATA_PATH = '../data/resources.json';
  const STATS_PATH = '../data/stats.json';
  const SEARCH_DEBOUNCE = 200;
  const DESC_TRUNCATE = 160;
  const MAX_TAGS_CLOUD = 50;
  const GITHUB_REPO = 'ai-research-hub/ai-research-hub';
  const STAGGER_DELAY = 50;

  const TYPE_COLORS = {
    tool: '#3b82f6', website: '#8b5cf6', tutorial: '#10b981', blog: '#f59e0b',
    video: '#ef4444', podcast: '#a855f7', presentation: '#06b6d4', paper: '#6366f1',
    course: '#14b8a6', dataset: '#f97316', library: '#22c55e', framework: '#e11d48',
    newsletter: '#eab308', community: '#ec4899', other: '#64748b',
  };

  const ACCESS_LABELS = {
    free: 'Free', freemium: 'Freemium', paid: 'Paid',
    'open-access': 'Open Access', unknown: 'Unknown',
  };

  // ─── State ──────────────────────────────────────────────────
  let allResources = [];
  let filteredResources = [];
  let pagefindAvailable = false;

  const state = {
    search: '',
    sort: 'newest',
    types: [],
    access: [],
    tags: [],
    addedBy: [],
    language: '',
    yearMin: 2018,
    yearMax: 2026,
  };

  // ─── DOM References ─────────────────────────────────────────
  const $ = (sel, ctx = document) => ctx.querySelector(sel);
  const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

  const dom = {
    searchInput: $('#search-input'),
    searchClear: $('#search-clear'),
    sortSelect: $('#sort-select'),
    filterToggle: $('#filter-toggle'),
    filterCount: $('#filter-count'),
    sidebar: $('#sidebar'),
    sidebarOverlay: $('#sidebar-overlay'),
    clearFilters: $('#clear-filters'),
    activeFilters: $('#active-filters'),
    activeFiltersList: $('#active-filters-list'),
    typeFilters: $('#type-filters'),
    accessFilters: $('#access-filters'),
    yearMin: $('#year-min'),
    yearMax: $('#year-max'),
    yearMinDisplay: $('#year-min-display'),
    yearMaxDisplay: $('#year-max-display'),
    addedByFilters: $('#added-by-filters'),
    languageFilter: $('#language-filter'),
    tagCloud: $('#tag-cloud'),
    resourceGrid: $('#resource-grid'),
    resultsCount: $('#results-count'),
    emptyState: $('#empty-state'),
    emptyClear: $('#empty-clear'),
    loadingState: $('#loading-state'),
    errorState: $('#error-state'),
    errorRetry: $('#error-retry'),
    suggestBtn: $('#suggest-btn'),
    submitModal: $('#submit-modal'),
    modalClose: $('#modal-close'),
    modalCancel: $('#modal-cancel'),
    submitForm: $('#submit-form'),
    themeToggle: $('#theme-toggle'),
    statTotal: $('#stat-total .stat-value'),
    statTypes: $('#stat-types .stat-value'),
    statUpdated: $('#stat-updated .stat-value'),
    statContributors: $('#stat-contributors .stat-value'),
  };

  // ─── Theme Management ──────────────────────────────────────
  function initTheme() {
    const saved = localStorage.getItem('theme');
    if (saved) {
      document.documentElement.setAttribute('data-theme', saved);
    } else {
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      document.documentElement.setAttribute('data-theme', prefersDark ? 'dark' : 'light');
    }
  }

  function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme');
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('theme', next);
  }

  // ─── Data Loading ──────────────────────────────────────────
  async function loadResources() {
    try {
      const resp = await fetch(DATA_PATH);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      allResources = Array.isArray(data) ? data : (data.resources || []);
      allResources = allResources.filter(r => !r.archived);
      return true;
    } catch (err) {
      console.error('Failed to load resources:', err);
      return false;
    }
  }

  async function loadStats() {
    try {
      const resp = await fetch(STATS_PATH);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const stats = await resp.json();
      dom.statTotal.textContent = stats.total_resources ?? allResources.length;
      dom.statTypes.textContent = stats.resource_types ?? new Set(allResources.map(r => r.type)).size;
      dom.statUpdated.textContent = stats.last_updated ? formatDate(stats.last_updated) : '—';
      dom.statContributors.textContent = stats.contributors ?? '—';
    } catch {
      dom.statTotal.textContent = allResources.length;
      dom.statTypes.textContent = new Set(allResources.map(r => r.type)).size;
      dom.statUpdated.textContent = '—';
      dom.statContributors.textContent = '—';
    }
  }

  // ─── Pagefind Integration ──────────────────────────────────
  async function initPagefind() {
    if (window.__pagefindUnavailable) {
      pagefindAvailable = false;
      return;
    }
    try {
      if (window.pagefind) {
        await window.pagefind.init();
        pagefindAvailable = true;
      }
    } catch {
      pagefindAvailable = false;
    }
  }

  // ─── Filter Population ────────────────────────────────────
  function populateFilters() {
    // Types
    const typeCounts = {};
    allResources.forEach(r => {
      typeCounts[r.type] = (typeCounts[r.type] || 0) + 1;
    });
    const sortedTypes = Object.entries(typeCounts).sort((a, b) => b[1] - a[1]);
    dom.typeFilters.innerHTML = sortedTypes.map(([type, count]) => `
      <label class="filter-check">
        <input type="checkbox" value="${type}" data-filter-type="type">
        <span class="filter-check-label">${capitalize(type)}</span>
        <span class="filter-check-count">${count}</span>
      </label>
    `).join('');

    // Access
    const accessCounts = {};
    allResources.forEach(r => {
      const a = r.access || 'unknown';
      accessCounts[a] = (accessCounts[a] || 0) + 1;
    });
    dom.accessFilters.innerHTML = Object.entries(accessCounts)
      .sort((a, b) => b[1] - a[1])
      .map(([access, count]) => `
        <label class="filter-check">
          <input type="checkbox" value="${access}" data-filter-type="access">
          <span class="filter-check-label">${ACCESS_LABELS[access] || capitalize(access)}</span>
          <span class="filter-check-count">${count}</span>
        </label>
      `).join('');

    // Added By
    dom.addedByFilters.innerHTML = ['human', 'agent'].map(val => `
      <label class="filter-check">
        <input type="checkbox" value="${val}" data-filter-type="added_by">
        <span class="filter-check-label">${capitalize(val)}</span>
        <span class="filter-check-count">${allResources.filter(r => r.added_by === val).length}</span>
      </label>
    `).join('');

    // Languages
    const languages = [...new Set(allResources.map(r => r.language).filter(Boolean))].sort();
    dom.languageFilter.innerHTML = '<option value="">All Languages</option>' +
      languages.map(l => `<option value="${l}">${l}</option>`).join('');

    // Year range
    const years = allResources.map(r => r.year).filter(Boolean);
    if (years.length) {
      const minYear = Math.min(...years);
      const maxYear = Math.max(...years);
      dom.yearMin.min = dom.yearMax.min = minYear;
      dom.yearMin.max = dom.yearMax.max = maxYear;
      dom.yearMin.value = state.yearMin = minYear;
      dom.yearMax.value = state.yearMax = maxYear;
      dom.yearMinDisplay.textContent = minYear;
      dom.yearMaxDisplay.textContent = maxYear;
    }

    // Tag cloud (top 50)
    const tagCounts = {};
    allResources.forEach(r => {
      (r.tags || []).forEach(t => {
        tagCounts[t] = (tagCounts[t] || 0) + 1;
      });
    });
    const topTags = Object.entries(tagCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, MAX_TAGS_CLOUD);

    dom.tagCloud.innerHTML = topTags.map(([tag]) => `
      <button class="tag-pill" data-tag="${escapeHtml(tag)}" type="button"
              aria-pressed="false" aria-label="Filter by tag: ${escapeHtml(tag)}">
        ${escapeHtml(tag)}
      </button>
    `).join('');
  }

  // ─── Filtering & Sorting ──────────────────────────────────
  function applyFilters() {
    let results = [...allResources];

    // Search (client-side fallback)
    if (state.search) {
      const q = state.search.toLowerCase();
      results = results.filter(r =>
        r.title.toLowerCase().includes(q) ||
        (r.description || '').toLowerCase().includes(q) ||
        (r.tags || []).some(t => t.toLowerCase().includes(q)) ||
        (r.authors || []).some(a => a.toLowerCase().includes(q)) ||
        (r.institution || '').toLowerCase().includes(q)
      );
    }

    // Type filter
    if (state.types.length) {
      results = results.filter(r => state.types.includes(r.type));
    }

    // Access filter
    if (state.access.length) {
      results = results.filter(r => state.access.includes(r.access || 'unknown'));
    }

    // Added by
    if (state.addedBy.length) {
      results = results.filter(r => state.addedBy.includes(r.added_by));
    }

    // Language
    if (state.language) {
      results = results.filter(r => r.language === state.language);
    }

    // Year range
    results = results.filter(r => {
      if (!r.year) return true;
      return r.year >= state.yearMin && r.year <= state.yearMax;
    });

    // Tags (AND logic)
    if (state.tags.length) {
      results = results.filter(r =>
        state.tags.every(t => (r.tags || []).includes(t))
      );
    }

    // Sort
    results = sortResources(results, state.sort);

    filteredResources = results;
    renderResults();
    updateResultsCount();
    updateActiveFilters();
    syncURL();
  }

  function sortResources(arr, method) {
    const copy = [...arr];
    switch (method) {
      case 'newest':
        return copy.sort((a, b) => (b.added_date || '').localeCompare(a.added_date || ''));
      case 'oldest':
        return copy.sort((a, b) => (a.added_date || '').localeCompare(b.added_date || ''));
      case 'quality':
        return copy.sort((a, b) => (b.quality_score ?? 0) - (a.quality_score ?? 0));
      case 'az':
        return copy.sort((a, b) => a.title.localeCompare(b.title));
      default:
        return copy;
    }
  }

  // ─── Rendering ─────────────────────────────────────────────
  function renderResults() {
    dom.loadingState.hidden = true;
    dom.errorState.hidden = true;

    if (filteredResources.length === 0) {
      dom.resourceGrid.innerHTML = '';
      dom.emptyState.hidden = false;
      return;
    }

    dom.emptyState.hidden = true;
    dom.resourceGrid.innerHTML = filteredResources.map((r, i) => renderCard(r, i)).join('');

    // Attach card event listeners
    dom.resourceGrid.querySelectorAll('.expand-btn').forEach(btn => {
      btn.addEventListener('click', handleExpandDescription);
    });

    dom.resourceGrid.querySelectorAll('.card-tag').forEach(tag => {
      tag.addEventListener('click', () => {
        const tagValue = tag.dataset.tag;
        toggleTag(tagValue);
      });
    });
  }

  function renderCard(resource, index) {
    const typeColor = TYPE_COLORS[resource.type] || TYPE_COLORS.other;
    const desc = resource.description || '';
    const truncated = desc.length > DESC_TRUNCATE;
    const displayDesc = truncated ? desc.slice(0, DESC_TRUNCATE) + '…' : desc;
    const delay = Math.min(index * STAGGER_DELAY, 1000);

    const qualityScore = resource.quality_score ?? 0;
    const qualitySegments = Array.from({ length: 5 }, (_, i) =>
      `<span class="quality-segment${i < Math.round(qualityScore / 2) ? ' filled' : ''}"></span>`
    ).join('');

    return `
      <article class="resource-card" style="animation-delay:${delay}ms"
               data-pagefind-meta="title:${escapeAttr(resource.title)}, type:${resource.type}"
               data-pagefind-filter="type:${resource.type}, access:${resource.access || 'unknown'}">
        <div class="card-header">
          <h3 class="card-title">
            <a href="${escapeAttr(resource.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(resource.title)}</a>
          </h3>
          <a href="${escapeAttr(resource.url)}" target="_blank" rel="noopener noreferrer" class="card-external" aria-label="Open ${escapeAttr(resource.title)} in new tab">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true"><path d="M5 2h7v7M12 2L6 8" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/><path d="M11 8.5v3a1.5 1.5 0 0 1-1.5 1.5h-7A1.5 1.5 0 0 1 1 11.5v-7A1.5 1.5 0 0 1 2.5 3H6" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
          </a>
        </div>

        <div class="card-badges">
          <span class="type-badge" style="background:${typeColor}15;color:${typeColor}">${capitalize(resource.type)}</span>
          ${resource.access ? `<span class="access-badge ${resource.access}">${ACCESS_LABELS[resource.access] || resource.access}</span>` : ''}
          ${resource.added_by === 'agent' ? `<span class="agent-badge"><svg viewBox="0 0 10 10" fill="none"><circle cx="5" cy="5" r="3.5" stroke="currentColor" stroke-width="1"/><circle cx="5" cy="5" r="1" fill="currentColor"/></svg>Agent</span>` : ''}
        </div>

        ${desc ? `<p class="card-description" data-full="${escapeAttr(desc)}">${escapeHtml(displayDesc)}${truncated ? `<button class="expand-btn" type="button" aria-label="Show full description">more</button>` : ''}</p>` : ''}

        ${(resource.tags || []).length ? `
          <div class="card-tags">
            ${resource.tags.slice(0, 5).map(t => `<button class="card-tag" data-tag="${escapeAttr(t)}" type="button" aria-label="Filter by tag: ${escapeAttr(t)}">${escapeHtml(t)}</button>`).join('')}
            ${resource.tags.length > 5 ? `<span class="card-tag" style="cursor:default;opacity:0.6">+${resource.tags.length - 5}</span>` : ''}
          </div>
        ` : ''}

        <div class="card-meta">
          ${resource.year ? `<span class="card-meta-item">${resource.year}</span>` : ''}
          ${resource.institution ? `<span class="card-meta-item">${escapeHtml(resource.institution)}</span>` : ''}
          ${resource.authors?.length ? `<span class="card-meta-item">${escapeHtml(resource.authors[0])}${resource.authors.length > 1 ? ` +${resource.authors.length - 1}` : ''}</span>` : ''}
          <span class="quality-indicator" title="Quality: ${qualityScore}/10">
            <div class="quality-bar">${qualitySegments}</div>
            <span>${qualityScore.toFixed(1)}</span>
          </span>
        </div>
      </article>
    `;
  }

  function updateResultsCount() {
    const total = allResources.length;
    const shown = filteredResources.length;
    if (total === shown) {
      dom.resultsCount.innerHTML = `Showing all <strong>${total}</strong> resources`;
    } else {
      dom.resultsCount.innerHTML = `Showing <strong>${shown}</strong> of <strong>${total}</strong> resources`;
    }
  }

  // ─── Active Filters Display ────────────────────────────────
  function updateActiveFilters() {
    const pills = [];

    state.types.forEach(t => pills.push({ label: capitalize(t), group: 'types', value: t }));
    state.access.forEach(a => pills.push({ label: ACCESS_LABELS[a] || a, group: 'access', value: a }));
    state.tags.forEach(t => pills.push({ label: t, group: 'tags', value: t }));
    state.addedBy.forEach(a => pills.push({ label: capitalize(a), group: 'addedBy', value: a }));
    if (state.language) pills.push({ label: state.language, group: 'language', value: state.language });

    const activeCount = pills.length;
    dom.filterCount.textContent = activeCount;
    dom.filterCount.hidden = activeCount === 0;
    dom.activeFilters.hidden = activeCount === 0;

    dom.activeFiltersList.innerHTML = pills.map(p => `
      <button class="active-filter-tag" data-group="${p.group}" data-value="${escapeAttr(p.value)}" aria-label="Remove filter: ${escapeAttr(p.label)}">
        ${escapeHtml(p.label)}
        <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true"><path d="M2 2l6 6M8 2l-6 6" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>
      </button>
    `).join('');

    // Attach remove listeners
    dom.activeFiltersList.querySelectorAll('.active-filter-tag').forEach(btn => {
      btn.addEventListener('click', () => {
        removeFilter(btn.dataset.group, btn.dataset.value);
      });
    });
  }

  function removeFilter(group, value) {
    switch (group) {
      case 'types':
        state.types = state.types.filter(t => t !== value);
        uncheckFilterInput('type', value);
        break;
      case 'access':
        state.access = state.access.filter(a => a !== value);
        uncheckFilterInput('access', value);
        break;
      case 'tags':
        state.tags = state.tags.filter(t => t !== value);
        updateTagCloudUI();
        break;
      case 'addedBy':
        state.addedBy = state.addedBy.filter(a => a !== value);
        uncheckFilterInput('added_by', value);
        break;
      case 'language':
        state.language = '';
        dom.languageFilter.value = '';
        break;
    }
    applyFilters();
  }

  function uncheckFilterInput(type, value) {
    const input = dom.sidebar.querySelector(`input[data-filter-type="${type}"][value="${CSS.escape(value)}"]`);
    if (input) input.checked = false;
  }

  // ─── URL Sync ──────────────────────────────────────────────
  function syncURL() {
    const params = new URLSearchParams();

    if (state.search) params.set('q', state.search);
    if (state.sort !== 'newest') params.set('sort', state.sort);
    if (state.types.length) params.set('type', state.types.join(','));
    if (state.access.length) params.set('access', state.access.join(','));
    if (state.tags.length) params.set('tags', state.tags.join(','));
    if (state.addedBy.length) params.set('by', state.addedBy.join(','));
    if (state.language) params.set('lang', state.language);

    const years = allResources.map(r => r.year).filter(Boolean);
    const dataMin = years.length ? Math.min(...years) : 2018;
    const dataMax = years.length ? Math.max(...years) : 2026;
    if (state.yearMin !== dataMin) params.set('ymin', state.yearMin);
    if (state.yearMax !== dataMax) params.set('ymax', state.yearMax);

    const qs = params.toString();
    const newUrl = qs ? `${location.pathname}?${qs}` : location.pathname;
    history.replaceState(null, '', newUrl);
  }

  function readURL() {
    const params = new URLSearchParams(location.search);

    if (params.has('q')) {
      state.search = params.get('q');
      dom.searchInput.value = state.search;
    }

    if (params.has('sort')) {
      state.sort = params.get('sort');
      dom.sortSelect.value = state.sort;
    }

    if (params.has('type')) {
      state.types = params.get('type').split(',').filter(Boolean);
    }

    if (params.has('access')) {
      state.access = params.get('access').split(',').filter(Boolean);
    }

    if (params.has('tags')) {
      state.tags = params.get('tags').split(',').filter(Boolean);
    }

    if (params.has('by')) {
      state.addedBy = params.get('by').split(',').filter(Boolean);
    }

    if (params.has('lang')) {
      state.language = params.get('lang');
      dom.languageFilter.value = state.language;
    }

    if (params.has('ymin')) {
      state.yearMin = parseInt(params.get('ymin'), 10);
      dom.yearMin.value = state.yearMin;
      dom.yearMinDisplay.textContent = state.yearMin;
    }

    if (params.has('ymax')) {
      state.yearMax = parseInt(params.get('ymax'), 10);
      dom.yearMax.value = state.yearMax;
      dom.yearMaxDisplay.textContent = state.yearMax;
    }

    // Restore checkbox state
    state.types.forEach(t => {
      const el = dom.sidebar.querySelector(`input[data-filter-type="type"][value="${CSS.escape(t)}"]`);
      if (el) el.checked = true;
    });
    state.access.forEach(a => {
      const el = dom.sidebar.querySelector(`input[data-filter-type="access"][value="${CSS.escape(a)}"]`);
      if (el) el.checked = true;
    });
    state.addedBy.forEach(a => {
      const el = dom.sidebar.querySelector(`input[data-filter-type="added_by"][value="${CSS.escape(a)}"]`);
      if (el) el.checked = true;
    });

    updateTagCloudUI();
    updateSearchClear();
  }

  // ─── Event Handlers ────────────────────────────────────────

  // Search
  let searchTimer;
  function handleSearch() {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.search = dom.searchInput.value.trim();
      updateSearchClear();
      applyFilters();
    }, SEARCH_DEBOUNCE);
  }

  function updateSearchClear() {
    dom.searchClear.hidden = !dom.searchInput.value;
  }

  function handleSearchClear() {
    dom.searchInput.value = '';
    state.search = '';
    dom.searchClear.hidden = true;
    dom.searchInput.focus();
    applyFilters();
  }

  // Sort
  function handleSort() {
    state.sort = dom.sortSelect.value;
    applyFilters();
  }

  // Filter checkboxes
  function handleFilterChange(e) {
    const input = e.target;
    if (input.tagName !== 'INPUT' || input.type !== 'checkbox') return;

    const filterType = input.dataset.filterType;
    const value = input.value;

    if (filterType === 'type') {
      state.types = input.checked
        ? [...state.types, value]
        : state.types.filter(t => t !== value);
    } else if (filterType === 'access') {
      state.access = input.checked
        ? [...state.access, value]
        : state.access.filter(a => a !== value);
    } else if (filterType === 'added_by') {
      state.addedBy = input.checked
        ? [...state.addedBy, value]
        : state.addedBy.filter(a => a !== value);
    }

    applyFilters();
  }

  // Year slider
  function handleYearChange() {
    let min = parseInt(dom.yearMin.value, 10);
    let max = parseInt(dom.yearMax.value, 10);
    if (min > max) [min, max] = [max, min];
    state.yearMin = min;
    state.yearMax = max;
    dom.yearMinDisplay.textContent = min;
    dom.yearMaxDisplay.textContent = max;
    applyFilters();
  }

  // Language
  function handleLanguageChange() {
    state.language = dom.languageFilter.value;
    applyFilters();
  }

  // Tags
  function toggleTag(tag) {
    if (state.tags.includes(tag)) {
      state.tags = state.tags.filter(t => t !== tag);
    } else {
      state.tags = [...state.tags, tag];
    }
    updateTagCloudUI();
    applyFilters();
  }

  function updateTagCloudUI() {
    dom.tagCloud.querySelectorAll('.tag-pill').forEach(pill => {
      const active = state.tags.includes(pill.dataset.tag);
      pill.classList.toggle('active', active);
      pill.setAttribute('aria-pressed', active);
    });
  }

  // Expand description
  function handleExpandDescription(e) {
    const btn = e.currentTarget;
    const descEl = btn.closest('.card-description');
    if (!descEl) return;
    const full = descEl.dataset.full;
    descEl.textContent = full;
  }

  // Filter section collapse
  function handleFilterCollapse(e) {
    const btn = e.currentTarget;
    const expanded = btn.getAttribute('aria-expanded') === 'true';
    btn.setAttribute('aria-expanded', !expanded);
    const body = btn.closest('.filter-group').querySelector('.filter-body');
    body.classList.toggle('collapsed', expanded);
  }

  // Mobile sidebar
  function handleFilterToggle() {
    const isOpen = dom.sidebar.classList.contains('open');
    dom.sidebar.classList.toggle('open', !isOpen);
    dom.sidebarOverlay.classList.toggle('visible', !isOpen);
    dom.filterToggle.setAttribute('aria-expanded', !isOpen);
    if (!isOpen) {
      dom.sidebarOverlay.style.display = 'block';
    } else {
      setTimeout(() => { dom.sidebarOverlay.style.display = 'none'; }, 250);
    }
  }

  function closeSidebar() {
    dom.sidebar.classList.remove('open');
    dom.sidebarOverlay.classList.remove('visible');
    dom.filterToggle.setAttribute('aria-expanded', 'false');
    setTimeout(() => { dom.sidebarOverlay.style.display = 'none'; }, 250);
  }

  // Clear all filters
  function clearAllFilters() {
    state.search = '';
    state.types = [];
    state.access = [];
    state.tags = [];
    state.addedBy = [];
    state.language = '';

    const years = allResources.map(r => r.year).filter(Boolean);
    state.yearMin = years.length ? Math.min(...years) : 2018;
    state.yearMax = years.length ? Math.max(...years) : 2026;

    dom.searchInput.value = '';
    dom.searchClear.hidden = true;
    dom.sortSelect.value = 'newest';
    state.sort = 'newest';
    dom.languageFilter.value = '';
    dom.yearMin.value = state.yearMin;
    dom.yearMax.value = state.yearMax;
    dom.yearMinDisplay.textContent = state.yearMin;
    dom.yearMaxDisplay.textContent = state.yearMax;

    dom.sidebar.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = false);
    updateTagCloudUI();
    applyFilters();
  }

  // ─── Submit Modal ──────────────────────────────────────────
  function openModal() {
    dom.submitModal.showModal();
  }

  function closeModal() {
    dom.submitModal.close();
    dom.submitForm.reset();
    clearFormErrors();
  }

  function handleSubmit(e) {
    e.preventDefault();
    clearFormErrors();

    const url = $('#submit-url').value.trim();
    const title = $('#submit-title').value.trim();
    const type = $('#submit-type').value;
    const tags = $('#submit-tags').value.trim();
    const desc = $('#submit-desc').value.trim();

    let valid = true;

    if (!url || !isValidUrl(url)) {
      showFieldError('url', 'Please enter a valid URL');
      valid = false;
    }
    if (!title) {
      showFieldError('title', 'Title is required');
      valid = false;
    }
    if (!type) {
      $('#submit-type').classList.add('invalid');
      valid = false;
    }

    if (!valid) return;

    // Build GitHub issue URL
    const issueTitle = `[Resource] ${title}`;
    const issueBody = [
      `## Suggested Resource`,
      ``,
      `**URL:** ${url}`,
      `**Title:** ${title}`,
      `**Type:** ${type}`,
      tags ? `**Tags:** ${tags}` : '',
      desc ? `**Description:** ${desc}` : '',
      ``,
      `---`,
      `_Submitted via AI Research Hub_`,
    ].filter(Boolean).join('\n');

    const issueUrl = `https://github.com/${GITHUB_REPO}/issues/new?` +
      new URLSearchParams({ title: issueTitle, body: issueBody, labels: 'resource-suggestion' }).toString();

    window.open(issueUrl, '_blank', 'noopener,noreferrer');
    closeModal();
  }

  function showFieldError(field, msg) {
    const input = $(`#submit-${field}`);
    const error = $(`#${field}-error`);
    if (input) input.classList.add('invalid');
    if (error) error.textContent = msg;
  }

  function clearFormErrors() {
    dom.submitForm.querySelectorAll('.invalid').forEach(el => el.classList.remove('invalid'));
    dom.submitForm.querySelectorAll('.form-hint').forEach(el => el.textContent = '');
  }

  function isValidUrl(str) {
    try {
      const u = new URL(str);
      return u.protocol === 'http:' || u.protocol === 'https:';
    } catch {
      return false;
    }
  }

  // ─── Utilities ─────────────────────────────────────────────
  function capitalize(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
  }

  function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  function escapeAttr(str) {
    return String(str).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function formatDate(dateStr) {
    try {
      const d = new Date(dateStr);
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    } catch {
      return dateStr;
    }
  }

  // ─── Initialization ───────────────────────────────────────
  async function init() {
    initTheme();
    await initPagefind();

    const success = await loadResources();

    if (!success) {
      dom.loadingState.hidden = true;
      dom.errorState.hidden = false;
      return;
    }

    populateFilters();
    readURL();
    await loadStats();
    applyFilters();

    // Bind events
    dom.searchInput.addEventListener('input', handleSearch);
    dom.searchClear.addEventListener('click', handleSearchClear);
    dom.sortSelect.addEventListener('change', handleSort);
    dom.themeToggle.addEventListener('click', toggleTheme);
    dom.filterToggle.addEventListener('click', handleFilterToggle);
    dom.sidebarOverlay.addEventListener('click', closeSidebar);
    dom.clearFilters.addEventListener('click', clearAllFilters);
    dom.emptyClear.addEventListener('click', clearAllFilters);
    dom.errorRetry.addEventListener('click', () => { location.reload(); });
    dom.suggestBtn.addEventListener('click', openModal);
    dom.modalClose.addEventListener('click', closeModal);
    dom.modalCancel.addEventListener('click', closeModal);
    dom.submitForm.addEventListener('submit', handleSubmit);
    dom.languageFilter.addEventListener('change', handleLanguageChange);
    dom.yearMin.addEventListener('input', handleYearChange);
    dom.yearMax.addEventListener('input', handleYearChange);

    // Filter checkbox delegation
    dom.sidebar.addEventListener('change', handleFilterChange);

    // Tag cloud delegation
    dom.tagCloud.addEventListener('click', (e) => {
      const pill = e.target.closest('.tag-pill');
      if (pill) toggleTag(pill.dataset.tag);
    });

    // Filter section collapse
    dom.sidebar.querySelectorAll('.filter-toggle-btn').forEach(btn => {
      btn.addEventListener('click', handleFilterCollapse);
    });

    // Close modal on backdrop click
    dom.submitModal.addEventListener('click', (e) => {
      if (e.target === dom.submitModal) closeModal();
    });

    // Keyboard: ESC closes modal & sidebar
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        if (dom.submitModal.open) closeModal();
        if (dom.sidebar.classList.contains('open')) closeSidebar();
      }
    });

    // Handle browser back/forward
    window.addEventListener('popstate', () => {
      readURL();
      applyFilters();
    });
  }

  // Boot
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
