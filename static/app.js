/**
 * Skyfall OSINT Helper — frontend logic.
 *
 * What it does:
 *   1. Checks /api/health — whether Ollama is alive.
 *   2. Listens for form submission, sends a POST to /api/investigate.
 *   3. Shows progress, renders the result.
 *   4. Runs a "live" investigation: a graph with nodes and edges,
 *      manual nodes, notes, a source for every node.
 *   5. Lets you add new searches to the graph of a past investigation.
 *   6. Saves the whole analysis page as HTML (saved_pages/).
 *
 * Rendering — via createElement/textContent, not innerHTML with user
 * data, to avoid XSS.
 */

'use strict';

const UI_LOCALE = (window.__LANG__ === 'en') ? 'en-GB' : 'ru-RU';

// Web localization helpers (defined in static/i18n.js).
const tr = window.tr || ((text) => text);
const tf = window.tf || ((text, vars) => {
  let out = text;
  for (const [key, value] of Object.entries(vars || {})) {
    out = out.split(`{${key}}`).join(String(value));
  }
  return out;
});

// ============================================================
// DOM ELEMENTS
// ============================================================

const form          = document.getElementById('investigate-form');
const valueInput    = document.getElementById('value');
const valueLabel    = document.getElementById('valueLabel');
const valueHint     = document.getElementById('valueHint');
const submitBtn     = document.getElementById('submit-btn');
const progressEl    = document.getElementById('progress');
const progressTitle = document.getElementById('progressTitle');
const progressHint  = document.getElementById('progressHint');
const errorEl       = document.getElementById('error');
const errorTextEl   = document.getElementById('errorText');
const resultEl      = document.getElementById('result');

// Meta
const metaCard      = document.getElementById('metaCard');
const metaInput     = document.getElementById('metaInput');
const metaType      = document.getElementById('metaType');
const metaTime      = document.getElementById('metaTime');
const metaPath      = document.getElementById('metaPath');

// Summary
const summaryCard   = document.getElementById('summaryCard');
const summaryText   = document.getElementById('summaryText');

// Reasoning
const thinkingCard  = document.getElementById('thinkingCard');
const thinkingText  = document.getElementById('thinkingText');

// Entities
const entitiesCard  = document.getElementById('entitiesCard');
const entitiesCount = document.getElementById('entitiesCount');
const entitiesList  = document.getElementById('entitiesList');

// Connections
const connectionsCard  = document.getElementById('connectionsCard');
const connectionsCount = document.getElementById('connectionsCount');
const connectionsList  = document.getElementById('connectionsList');

// Remarks
const notesCard           = document.getElementById('notesCard');
const contradictionsCol   = document.getElementById('contradictionsCol');
const contradictionsList  = document.getElementById('contradictionsList');
const uncertaintiesCol    = document.getElementById('uncertaintiesCol');
const uncertaintiesList   = document.getElementById('uncertaintiesList');

// Tree
const treeCard = document.getElementById('treeCard');
const treeRoot = document.getElementById('treeRoot');

// Filtering
const filterCard         = document.getElementById('filterCard');
const keptCount          = document.getElementById('keptCount');
const keptList           = document.getElementById('keptList');
const droppedBlock       = document.getElementById('droppedBlock');
const droppedCount       = document.getElementById('droppedCount');
const droppedList        = document.getElementById('droppedList');
const filterThinkingWrap = document.getElementById('filterThinkingWrap');
const filterThinking     = document.getElementById('filterThinking');

// Raw data
const rawCard = document.getElementById('rawCard');
const rawText = document.getElementById('rawText');

// Health / LLM
const healthDot  = document.querySelector('.health__dot');
const healthText = document.getElementById('healthText');
const llmBadge     = document.getElementById('llmBadge');
const llmBadgeDot  = document.getElementById('llmBadgeDot');
const llmBadgeText = document.getElementById('llmBadgeText');

// Raw Mode / logs
const rawModeCheckbox = document.getElementById('rawMode');
const metaMode        = document.getElementById('metaMode');
const downloadLogsBtn = document.getElementById('downloadLogsBtn');

// Investigation
const invBar        = document.getElementById('invBar');
const invTitle      = document.getElementById('invTitle');
const invMeta       = document.getElementById('invMeta');
const invSearches   = document.getElementById('invSearches');
const invSaved      = document.getElementById('invSaved');
const invDetailsCard = document.getElementById('invDetailsCard');
const invDetails    = document.getElementById('invDetails');
const savePageBtn   = document.getElementById('savePageBtn');

const targetInvestigation = document.getElementById('targetInvestigation');
const linkToField         = document.getElementById('linkToField');
const linkToNode          = document.getElementById('linkToNode');

// Graph
const graphCard        = document.getElementById('graphCard');
const graphContainer   = document.getElementById('graph');
const graphNodesCount  = document.getElementById('graphNodesCount');
const graphEdgesCount  = document.getElementById('graphEdgesCount');
const graphLinkHint    = document.getElementById('graphLinkHint');
const graphLinkHintText = document.getElementById('graphLinkHintText');
const addNodeBtn       = document.getElementById('addNodeBtn');
const linkModeBtn      = document.getElementById('linkModeBtn');
const relayoutBtn      = document.getElementById('relayoutBtn');
const fitGraphBtn      = document.getElementById('fitGraphBtn');
const cancelLinkBtn    = document.getElementById('cancelLinkBtn');

// Node modal
const nodeModal      = document.getElementById('nodeModal');
const nodeModalTitle = document.getElementById('nodeModalTitle');
const nodeForm       = document.getElementById('nodeForm');
const nodeIdInput    = document.getElementById('nodeId');
const nodeLabelInput = document.getElementById('nodeLabel');
const nodeTypeInput  = document.getElementById('nodeType');
const nodeNumInput   = document.getElementById('nodeNum');
const nodeUrlInput   = document.getElementById('nodeUrl');
const nodeDescInput  = document.getElementById('nodeDescription');
const nodeNotesInput = document.getElementById('nodeNotes');

// Investigations modal
const invModal       = document.getElementById('invModal');
const invListEl      = document.getElementById('invList');
const savedPagesList = document.getElementById('savedPagesList');
const openInvListBtn = document.getElementById('openInvListBtn');
const newInvBtn      = document.getElementById('newInvBtn');

// LLM settings
const openLlmSettingsBtn = document.getElementById('openLlmSettingsBtn');
const llmModal       = document.getElementById('llmModal');
const llmForm        = document.getElementById('llmForm');
const llmProvider    = document.getElementById('llmProvider');
const llmModel       = document.getElementById('llmModel');
const llmModelLabel  = document.getElementById('llmModelLabel');
const llmKeyField    = document.getElementById('llmKeyField');
const llmApiKey      = document.getElementById('llmApiKey');
const llmKeyHint     = document.getElementById('llmKeyHint');
const llmBaseField   = document.getElementById('llmBaseField');
const llmBaseUrl     = document.getElementById('llmBaseUrl');
const llmStatus      = document.getElementById('llmStatus');
const llmTestBtn     = document.getElementById('llmTestBtn');

// Notification
const toastEl   = document.getElementById('toast');
const toastText = document.getElementById('toastText');
const toastLink = document.getElementById('toastLink');

const SVG_NS = 'http://www.w3.org/2000/svg';
const NODE_HEIGHT = 46;

// ============================================================
// HELPERS
// ============================================================

/** Creates an element with a class and (optionally) text. */
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = String(text);
  return node;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

/** Keeps only safe link schemes. */
function safeHref(value) {
  const text = String(value || '').trim();
  return /^(https?:\/\/|mailto:)/i.test(text) ? text : '';
}

/** Formats an ISO date into a readable form. */
function formatDate(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso);
    return d.toLocaleString(UI_LOCALE, {
      year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return String(iso);
  }
}

function formatDateShort(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return d.toLocaleString(UI_LOCALE, {
      day: '2-digit', month: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return '';
  }
}

function truncate(str, max = 200) {
  if (str == null) return '';
  const s = String(str);
  return s.length > max ? s.slice(0, max) + '…' : s;
}

let toastTimer = null;

function showToast(message, options = {}) {
  toastText.textContent = String(message || '');
  toastEl.classList.toggle('toast--error', Boolean(options.error));
  toastEl.classList.remove('hidden');

  if (options.href) {
    toastLink.href = options.href;
    toastLink.textContent = options.linkLabel ? tr(options.linkLabel) : tr('Открыть');
    toastLink.classList.remove('hidden');
  } else {
    toastLink.classList.add('hidden');
    toastLink.removeAttribute('href');
  }

  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toastEl.classList.add('hidden'), options.timeout || 6500);
}

async function apiJson(url, options = {}) {
  const opts = Object.assign({}, options);
  opts.headers = Object.assign({ 'Content-Type': 'application/json' }, options.headers || {});
  if (opts.body && typeof opts.body !== 'string') {
    opts.body = JSON.stringify(opts.body);
  }

  const response = await fetch(url, opts);
  let data = null;
  try {
    data = await response.json();
  } catch {
    // ignore: the body may be empty
  }

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    if (data && data.detail) {
      detail = typeof data.detail === 'string'
        ? data.detail
        : JSON.stringify(data.detail);
    }
    throw new Error(detail);
  }
  return data;
}

function showProgress(show) {
  progressEl.classList.toggle('hidden', !show);
}

function showError(message) {
  errorTextEl.textContent = message;
  errorEl.classList.remove('hidden');
}

function hideError() {
  errorEl.classList.add('hidden');
}

function setLoading(loading) {
  submitBtn.disabled = loading;
  submitBtn.classList.toggle('is-loading', loading);
  const label = submitBtn.querySelector('.btn__label');
  if (label) {
    label.textContent = loading ? tr('Идёт расследование…') : tr('🔎 Расследовать');
  }
}

// ============================================================
// HEALTH CHECK
// ============================================================

async function checkHealth() {
  try {
    const r = await fetch('/api/health', { method: 'GET' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();

    const providerId = data.llm_provider || 'ollama';
    const provider = {
      ollama: 'Ollama',
      openai: 'OpenAI',
      openrouter: 'OpenRouter',
    }[providerId] || providerId;
    const model = data.llm_model || data.ollama_model || '—';
    const available = data.llm_available !== undefined
      ? Boolean(data.llm_available)
      : Boolean(data.ollama_available);

    llmBadge.classList.remove('hidden');
    llmBadgeDot.className = 'llm-badge__dot ' + (available ? 'is-ok' : 'is-fail');
    llmBadgeText.textContent = `${provider} · ${model}`;
    llmBadge.title = available
      ? tf('LLM доступна: {provider} / {model}', { provider, model })
      : tf('LLM недоступна: {provider} / {model}', { provider, model });

    if (available) {
      healthDot.className = 'health__dot health__dot--ok';
      healthText.textContent = `${provider}: ${model}`;
    } else {
      healthDot.className = 'health__dot health__dot--fail';
      healthText.textContent = tf('{provider} недоступна', { provider });
    }

    // If AI is disabled in the config, show that in the form.
    if (data.use_ai === false) {
      rawModeCheckbox.checked = true;
      rawModeCheckbox.disabled = true;
      const label = rawModeCheckbox.closest('.checkbox');
      if (label) {
        label.classList.add('checkbox--disabled');
        label.title = tr('AI отключён в config.py (USE_AI=False)');
      }
    }
  } catch (err) {
    healthDot.className = 'health__dot health__dot--fail';
    healthText.textContent = tr('Бэкенд недоступен');
    llmBadgeDot.className = 'llm-badge__dot is-fail';
    llmBadgeText.textContent = tr('LLM: нет связи');
    console.warn('[health]', err);
  }
}

// ============================================================
// RENDER: SUMMARY
// ============================================================

function renderSummary(analysis) {
  const text = analysis && typeof analysis.summary === 'string'
    ? analysis.summary.trim()
    : '';
  if (!text) return;
  summaryText.textContent = text;
  summaryCard.hidden = false;
}

function renderThinking(analysis) {
  const text = analysis && typeof analysis.thinking === 'string'
    ? analysis.thinking.trim()
    : '';
  if (!text) return;
  thinkingText.textContent = text;
  thinkingCard.hidden = false;
}

// ============================================================
// RENDER: ENTITIES
// ============================================================

function renderEntities(analysis) {
  const list = Array.isArray(analysis && analysis.entities)
    ? analysis.entities
    : [];
  if (!list.length) return;

  entitiesCount.textContent = String(list.length);

  for (const item of list) {
    if (!item || typeof item !== 'object') continue;

    const li = el('li', 'entity');

    const type = el('span', 'entity__type', item.type || '?');
    type.dataset.type = String(item.type || '').toLowerCase();
    li.appendChild(type);

    li.appendChild(el('span', 'entity__value', item.value || '?'));

    if (Array.isArray(item.found_in) && item.found_in.length) {
      const found = el('div', 'entity__found');
      found.textContent = tr('найдено в: ') + item.found_in.map(String).join(', ');
      li.appendChild(found);
    }

    entitiesList.appendChild(li);
  }

  entitiesCard.hidden = false;
}

// ============================================================
// RENDER: CONNECTIONS
// ============================================================

function renderConnections(analysis) {
  const list = Array.isArray(analysis && analysis.connections)
    ? analysis.connections
    : [];
  if (!list.length) return;

  connectionsCount.textContent = String(list.length);

  for (const c of list) {
    if (!c || typeof c !== 'object') continue;

    const conf = String(c.confidence || 'low').toLowerCase();
    const li = el('li', 'connection');
    li.dataset.confidence = conf;

    const head = el('div', 'connection__head');
    head.appendChild(el('span', 'connection__pair', c.entity_a || '?'));
    head.appendChild(el('span', 'connection__arrow', '↔'));
    head.appendChild(el('span', 'connection__pair', c.entity_b || '?'));

    const badge = el('span', 'confidence', conf);
    badge.dataset.level = conf;
    head.appendChild(badge);

    li.appendChild(head);

    if (c.evidence) {
      const row = el('div', 'connection__row');
      row.appendChild(el('strong', null, tr('Доказательство: ')));
      row.appendChild(document.createTextNode(truncate(c.evidence, 300)));
      li.appendChild(row);
    }

    if (c.reasoning) {
      const row = el('div', 'connection__row');
      row.appendChild(el('strong', null, tr('Почему: ')));
      row.appendChild(document.createTextNode(truncate(c.reasoning, 300)));
      li.appendChild(row);
    }

    connectionsList.appendChild(li);
  }

  connectionsCard.hidden = false;
}

// ============================================================
// RENDER: REMARKS
// ============================================================

function renderNotes(analysis) {
  const contradictions = Array.isArray(analysis && analysis.contradictions)
    ? analysis.contradictions
    : [];
  const uncertainties = Array.isArray(analysis && analysis.uncertainties)
    ? analysis.uncertainties
    : [];

  if (!contradictions.length && !uncertainties.length) return;

  if (contradictions.length) {
    for (const item of contradictions) {
      const li = document.createElement('li');
      li.textContent = typeof item === 'string' ? item : JSON.stringify(item);
      contradictionsList.appendChild(li);
    }
    contradictionsCol.hidden = false;
  }

  if (uncertainties.length) {
    for (const item of uncertainties) {
      const li = document.createElement('li');
      li.textContent = typeof item === 'string' ? item : JSON.stringify(item);
      uncertaintiesList.appendChild(li);
    }
    uncertaintiesCol.hidden = false;
  }

  notesCard.hidden = false;
}

// ============================================================
// RENDER: TREE
// ============================================================

function renderTreeNode(node) {
  if (typeof node === 'string') {
    const wrap = el('div', 'tree__node');
    wrap.appendChild(el('span', 'tree__label', node));
    return wrap;
  }

  if (!node || typeof node !== 'object') {
    return null;
  }

  const wrap = el('div', 'tree__node');
  wrap.appendChild(el('span', 'tree__label', node.node || '?'));

  if (node.confidence) {
    const level = String(node.confidence).toLowerCase();
    const badge = el('span', 'tree__confidence', level);
    badge.dataset.level = level;
    wrap.appendChild(badge);
  }

  if (Array.isArray(node.children) && node.children.length) {
    const children = el('div', 'tree__children');
    for (const child of node.children) {
      const childNode = renderTreeNode(child);
      if (childNode) children.appendChild(childNode);
    }
    wrap.appendChild(children);
  }

  return wrap;
}

function renderTree(analysis) {
  const tree = analysis && analysis.tree;
  if (!tree || typeof tree !== 'object') return;

  if (tree.root) {
    treeRoot.appendChild(el('div', 'tree__root', tree.root));
  }

  if (Array.isArray(tree.children)) {
    for (const child of tree.children) {
      const node = renderTreeNode(child);
      if (node) treeRoot.appendChild(node);
    }
  }

  treeCard.hidden = false;
}

// ============================================================
// RENDER: FILTERING
// ============================================================

function renderSiteData(siteEl, data) {
  if (!data || typeof data !== 'object') return;
  const keys = Object.keys(data);
  if (!keys.length) return;

  const box = el('div', 'site__data');
  for (const key of keys) {
    const value = data[key];
    if (value == null || value === '') continue;
    const row = el('div', 'site__data-row');
    row.appendChild(el('span', 'site__data-key', key + ':'));
    row.appendChild(el('span', null, truncate(value, 200)));
    box.appendChild(row);
  }

  if (box.childNodes.length) {
    siteEl.appendChild(box);
  }
}

function renderKeptSite(item) {
  const li = el('li', 'site');

  const head = el('div', 'site__head');
  head.appendChild(el('span', 'site__name', item.site || '?'));

  if (item.weight) {
    const w = String(item.weight).toLowerCase();
    const badge = el('span', 'site__weight', w);
    badge.dataset.weight = w;
    head.appendChild(badge);
  }

  li.appendChild(head);

  if (item.url) {
    const url = el('a', 'site__url', item.url);
    url.href = item.url;
    url.target = '_blank';
    url.rel = 'noopener noreferrer';
    li.appendChild(url);
  }

  if (item.reason) {
    li.appendChild(el('div', 'site__reason', item.reason));
  }

  renderSiteData(li, item.data);

  return li;
}

function renderDroppedSite(item) {
  const li = el('li', 'site');
  const head = el('div', 'site__head');
  head.appendChild(el('span', 'site__name', item.site || '?'));
  li.appendChild(head);

  if (item.url) {
    li.appendChild(el('div', 'site__url', item.url));
  }

  if (item.reason) {
    li.appendChild(el('div', 'site__reason', item.reason));
  }

  return li;
}

function renderFilter(filtered) {
  if (!filtered || typeof filtered !== 'object') return;

  const kept = Array.isArray(filtered.kept) ? filtered.kept : [];
  const dropped = Array.isArray(filtered.dropped) ? filtered.dropped : [];

  if (!kept.length && !dropped.length && !filtered.thinking) return;

  filterCard.hidden = false;

  keptCount.textContent = String(kept.length);
  for (const item of kept) {
    if (item && typeof item === 'object') {
      keptList.appendChild(renderKeptSite(item));
    }
  }

  if (dropped.length) {
    droppedCount.textContent = String(dropped.length);
    for (const item of dropped) {
      if (item && typeof item === 'object') {
        droppedList.appendChild(renderDroppedSite(item));
      }
    }
    droppedBlock.hidden = false;
  }

  if (filtered.thinking) {
    filterThinking.textContent = String(filtered.thinking);
    filterThinkingWrap.hidden = false;
  }
}

// ============================================================
// RENDER: RAW DATA
// ============================================================

function renderRaw(rawData) {
  if (rawData == null) {
    rawText.textContent = tr('(нет данных)');
    return;
  }
  try {
    rawText.textContent = JSON.stringify(rawData, null, 2);
  } catch {
    rawText.textContent = String(rawData);
  }
}

// ============================================================
// INVESTIGATION STATE
// ============================================================

const INV = {
  list: [],
  current: null,
  cache: new Map(),   // id -> investigation (for the "link to" select)
};

const GRAPH = {
  positions: new Map(),   // nodeId -> {x, y}
  view: { x: 0, y: 0, k: 1 },
  els: {
    nodes: new Map(),
    edges: new Map(),
    edgeMid: new Map(),
    world: null,
    svg: null,
    nodeLayer: null,
  },
  popup: null,            // {kind: 'node'|'edge', id}
  popupEl: null,
  link: null,             // {sourceId: string|null}
  drag: null,
  pan: null,
  needsLayout: false,
  saveTimer: null,
  pendingNodePosition: null,
};

const NODE_STYLES = {
  center:   { bg: '#6b1d1d', border: '#c53a3a' },
  nick:     { bg: '#15233b', border: '#3f6ea8' },
  email:    { bg: '#24331f', border: '#6f9a3f' },
  domain:   { bg: '#2a2344', border: '#7c5cd6' },
  url:      { bg: '#0e3836', border: '#1fb8a6' },
  telegram: { bg: '#0b2c3c', border: '#38bdf8' },
  custom:   { bg: '#232b38', border: '#8b9bb4' },
  unknown:  { bg: '#1a212c', border: '#475569' },
};

const TYPE_LABELS = {
  center: tr('субъект'),
  nick: tr('ник'),
  email: 'email',
  domain: tr('домен'),
  url: tr('ссылка'),
  telegram: 'telegram',
  custom: tr('своё звено'),
  unknown: tr('сущность'),
};

function currentNodes() {
  return (INV.current && Array.isArray(INV.current.nodes)) ? INV.current.nodes : [];
}

function currentEdges() {
  return (INV.current && Array.isArray(INV.current.edges)) ? INV.current.edges : [];
}

function getNodeById(id) {
  return currentNodes().find((node) => node.id === id) || null;
}

function getEdgeById(id) {
  return currentEdges().find((edge) => edge.id === id) || null;
}

function nodeWidth(node) {
  const label = String(node.label || '');
  const desc = String(node.description || '');
  const estimate = Math.max(label.length * 7.1, desc.length * 5.1) + 76;
  return Math.round(clamp(estimate, 148, 256));
}

function nodeStyle(type) {
  return NODE_STYLES[type] || NODE_STYLES.unknown;
}

function updateInvestigationFromResponse(data) {
  if (!data) return;
  if (data.investigation) {
    INV.current = data.investigation;
    INV.cache.set(data.investigation.id, data.investigation);
  }
}

// ============================================================
// INVESTIGATION API
// ============================================================

async function loadInvestigations() {
  try {
    const data = await apiJson('/api/investigations');
    INV.list = Array.isArray(data.items) ? data.items : [];
  } catch (err) {
    console.warn('[investigations]', err);
    INV.list = [];
  }
  populateTargetSelect();
  return INV.list;
}

function populateTargetSelect(preferredId) {
  const previous = preferredId !== undefined ? preferredId : targetInvestigation.value;

  const options = [['__new__', tr('＋ Новое расследование')]];
  for (const item of INV.list) {
    const label = tf('{title} — {nodes} зв. / {searches} поиск.', { title: item.title, nodes: item.node_count, searches: item.search_count });
    options.push([item.id, label]);
  }

  targetInvestigation.replaceChildren();
  for (const [value, label] of options) {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = label;
    targetInvestigation.appendChild(option);
  }

  const exists = options.some(([value]) => value === previous);
  targetInvestigation.value = exists ? previous : '__new__';
}

async function fetchInvestigation(id) {
  if (INV.cache.has(id)) {
    return INV.cache.get(id);
  }
  const inv = await apiJson(`/api/investigations/${id}`);
  INV.cache.set(id, inv);
  return inv;
}

async function updateLinkToField() {
  const target = targetInvestigation.value;

  if (!target || target === '__new__') {
    linkToField.classList.add('hidden');
    linkToNode.replaceChildren();
    const empty = document.createElement('option');
    empty.value = '';
    empty.textContent = tr('— без связи —');
    linkToNode.appendChild(empty);
    return;
  }

  try {
    const inv = await fetchInvestigation(target);
    const nodes = Array.isArray(inv.nodes) ? inv.nodes.slice() : [];
    nodes.sort((a, b) => (Number(a.num) || 0) - (Number(b.num) || 0));

    linkToField.classList.remove('hidden');
    const previous = linkToNode.value;
    linkToNode.replaceChildren();

    const empty = document.createElement('option');
    empty.value = '';
    empty.textContent = nodes.length ? tr('— без связи —') : tr('— в расследовании пока нет звеньев —');
    linkToNode.appendChild(empty);

    for (const node of nodes) {
      const option = document.createElement('option');
      option.value = node.id;
      option.textContent = `${node.num ? node.num + '. ' : ''}${node.label}`;
      linkToNode.appendChild(option);
    }

    if (nodes.some((node) => node.id === previous)) {
      linkToNode.value = previous;
    }
  } catch (err) {
    console.warn('[linkToField]', err);
    linkToField.classList.add('hidden');
  }
}

// ============================================================
// INVESTIGATION PANEL
// ============================================================

function renderInvBar() {
  if (!INV.current) {
    invBar.classList.add('hidden');
    invDetailsCard.hidden = true;
    return;
  }

  invBar.classList.remove('hidden');
  invDetailsCard.hidden = false;

  if (document.activeElement !== invTitle) {
    invTitle.value = INV.current.title || '';
  }

  const searches = Array.isArray(INV.current.searches) ? INV.current.searches : [];
  const nodes = currentNodes();
  const edges = currentEdges();
  invMeta.textContent = tf('{nodes} звеньев · {edges} связей · {searches} поисков', { nodes: nodes.length, edges: edges.length, searches: searches.length });

  invSearches.replaceChildren();
  const typeIcons = { username: '@', email: '✉', domain: '⌘' };
  for (const search of searches) {
    const chip = el('span', 'search-chip');
    chip.title = formatDate(search.at);
    chip.appendChild(el('span', 'search-chip__icon', typeIcons[search.input_type] || '•'));
    chip.appendChild(el('span', null, search.input));
    if (search.nodes_added || search.edges_added) {
      chip.appendChild(el(
        'span',
        'search-chip__added',
        `+${search.nodes_added || 0}/${search.edges_added || 0}`,
      ));
    }
    invSearches.appendChild(chip);
  }
}

function renderInvDetails() {
  if (!INV.current) {
    invDetailsCard.hidden = true;
    return;
  }

  const nodes = currentNodes();
  const edges = currentEdges();
  invDetailsCard.hidden = false;
  invDetails.replaceChildren();

  const nodesTitle = el('div', 'inv-details__group-title', tf('Звенья ({count})', { count: nodes.length }));
  invDetails.appendChild(nodesTitle);

  if (!nodes.length) {
    invDetails.appendChild(el('div', 'inv-empty', tr('Пока нет ни одного звена.')));
  }

  const sorted = nodes.slice().sort((a, b) => (Number(a.num) || 0) - (Number(b.num) || 0));
  for (const node of sorted) {
    const row = el('div', 'inv-detail');

    const head = el('div', 'inv-detail__head');
    head.appendChild(el('span', 'inv-detail__num', node.num != null ? node.num : '•'));
    head.appendChild(el('span', 'inv-detail__label', node.label || '?'));
    head.appendChild(el('span', 'inv-detail__type', TYPE_LABELS[node.type] || node.type || '?'));
    row.appendChild(head);

    if (node.url && safeHref(node.url)) {
      const link = el('a', 'inv-detail__link', node.url);
      link.href = safeHref(node.url);
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      row.appendChild(link);
    }

    if (node.notes) {
      row.appendChild(el('div', 'inv-detail__notes', node.notes));
    }

    if (node.origin) {
      row.appendChild(el('div', 'inv-detail__type', node.origin));
    }

    invDetails.appendChild(row);
  }

  const edgesTitle = el('div', 'inv-details__group-title', tf('Связи ({count})', { count: edges.length }));
  invDetails.appendChild(edgesTitle);

  if (!edges.length) {
    invDetails.appendChild(el('div', 'inv-empty', tr('Связей пока нет.')));
  }

  for (const edge of edges) {
    const a = getNodeById(edge.source);
    const b = getNodeById(edge.target);
    const row = el('div', 'inv-detail');
    const head = el('div', 'inv-detail__head');
    head.appendChild(el(
      'span',
      'inv-detail__label',
      `${a ? a.label : '?'} ↔ ${b ? b.label : '?'}`,
    ));
    head.appendChild(el('span', 'inv-detail__type', edge.confidence || ''));
    row.appendChild(head);

    if (edge.notes) {
      row.appendChild(el('div', 'inv-detail__notes', edge.notes));
    }
    if (edge.origin) {
      row.appendChild(el('div', 'inv-detail__type', edge.origin));
    }

    invDetails.appendChild(row);
  }
}

// ============================================================
// GRAPH: GEOMETRY
// ============================================================

function hashString(value) {
  let hash = 2166136261;
  const text = String(value || '');
  for (let i = 0; i < text.length; i += 1) {
    hash ^= text.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function trimPoint(cx, cy, width, height, targetX, targetY) {
  const dx = targetX - cx;
  const dy = targetY - cy;
  const len = Math.hypot(dx, dy) || 1;
  const ux = dx / len;
  const uy = dy / len;
  const scale = Math.min(
    (width / 2) / (Math.abs(ux) || 1e-6),
    (height / 2) / (Math.abs(uy) || 1e-6),
  );
  return { x: cx + ux * scale, y: cy + uy * scale };
}

function edgeGeometry(edge) {
  const a = getNodeById(edge.source);
  const b = getNodeById(edge.target);
  const pa = GRAPH.positions.get(edge.source);
  const pb = GRAPH.positions.get(edge.target);
  if (!a || !b || !pa || !pb) return null;

  const wa = nodeWidth(a);
  const wb = nodeWidth(b);
  const ca = { x: pa.x + wa / 2, y: pa.y + NODE_HEIGHT / 2 };
  const cb = { x: pb.x + wb / 2, y: pb.y + NODE_HEIGHT / 2 };

  const dx = cb.x - ca.x;
  const dy = cb.y - ca.y;
  if (Math.hypot(dx, dy) < 2) return null;

  const start = trimPoint(ca.x, ca.y, wa, NODE_HEIGHT, cb.x, cb.y);
  const end = trimPoint(cb.x, cb.y, wb, NODE_HEIGHT, ca.x, ca.y);

  const len = Math.hypot(dx, dy) || 1;
  const ux = dx / len;
  const uy = dy / len;

  const hash = hashString(edge.id);
  const bend = (hash % 2 === 0 ? 1 : -1) * (16 + (hash % 34));
  const control = {
    x: (start.x + end.x) / 2 + (-uy) * bend,
    y: (start.y + end.y) / 2 + (ux) * bend,
  };

  const mid = {
    x: (start.x + 2 * control.x + end.x) / 4,
    y: (start.y + 2 * control.y + end.y) / 4,
  };

  return {
    d: `M ${start.x.toFixed(2)} ${start.y.toFixed(2)} Q ${control.x.toFixed(2)} ${control.y.toFixed(2)} ${end.x.toFixed(2)} ${end.y.toFixed(2)}`,
    mid,
  };
}

// ============================================================
// GRAPH: LAYOUT
// ============================================================

function ensureGraphPositions(nodes) {
  const alive = new Set(nodes.map((node) => node.id));
  for (const key of Array.from(GRAPH.positions.keys())) {
    if (!alive.has(key)) GRAPH.positions.delete(key);
  }

  const missing = [];
  let hadCoords = 0;

  for (const node of nodes) {
    if (GRAPH.positions.has(node.id)) {
      hadCoords += 1;
      continue;
    }
    const x = Number(node.x);
    const y = Number(node.y);
    if (Number.isFinite(x) && Number.isFinite(y)) {
      GRAPH.positions.set(node.id, { x, y });
      hadCoords += 1;
    } else {
      missing.push(node);
    }
  }

  if (!missing.length) return;

  if (!hadCoords) {
    // A brand-new graph — lay it out with forces after initialization.
    const total = Math.max(missing.length, 1);
    missing.forEach((node, index) => {
      const angle = (2 * Math.PI * index) / total - Math.PI / 2;
      const radius = 260 + 16 * total;
      GRAPH.positions.set(node.id, {
        x: 480 + radius * Math.cos(angle),
        y: 380 + 180 * Math.sin(angle),
      });
    });
    GRAPH.needsLayout = true;
    return;
  }

  // Some nodes are already placed: new ones go next to a neighbor.
  for (const node of missing) {
    const edge = currentEdges().find(
      (item) => item.source === node.id || item.target === node.id,
    );
    let base = { x: 480, y: 380 };
    if (edge) {
      const otherId = edge.source === node.id ? edge.target : edge.source;
      const other = GRAPH.positions.get(otherId);
      if (other) base = other;
    }
    const angle = (GRAPH.positions.size * 2.399963) % (Math.PI * 2);
    GRAPH.positions.set(node.id, {
      x: base.x + 300 * Math.cos(angle),
      y: base.y + 170 * Math.sin(angle),
    });
  }
}

function runLayout(persist = true) {
  const nodes = currentNodes();
  const edges = currentEdges();
  const n = nodes.length;
  if (!n) return;

  const indexOf = new Map();
  nodes.forEach((node, index) => indexOf.set(node.id, index));

  const width = Math.max(1100, 240 * Math.sqrt(n) * 1.7);
  const height = Math.max(760, 150 * Math.sqrt(n) * 1.7);
  const k = Math.sqrt((width * height) / Math.max(n, 1)) * 0.85;

  const pos = nodes.map((node, index) => {
    const current = GRAPH.positions.get(node.id);
    if (current) return { x: current.x, y: current.y };
    const angle = (2 * Math.PI * index) / Math.max(n, 1);
    return {
      x: width / 2 + (width / 3) * Math.cos(angle),
      y: height / 2 + (height / 4) * Math.sin(angle),
    };
  });

  const disp = nodes.map(() => ({ x: 0, y: 0 }));
  let temperature = width / 8;
  const iterations = n > 80 ? 150 : 300;

  for (let step = 0; step < iterations; step += 1) {
    for (const item of disp) {
      item.x = 0;
      item.y = 0;
    }

    // Repulsion between every pair of nodes.
    for (let i = 0; i < n; i += 1) {
      for (let j = i + 1; j < n; j += 1) {
        let dx = pos[i].x - pos[j].x;
        let dy = pos[i].y - pos[j].y;
        let dist = Math.hypot(dx, dy);
        if (dist < 0.01) {
          dx = (Math.random() - 0.5) * 2;
          dy = (Math.random() - 0.5) * 2;
          dist = Math.hypot(dx, dy) || 1;
        }
        if (dist > width * 2) continue;
        const force = (k * k) / dist;
        const ux = dx / dist;
        const uy = dy / dist;
        disp[i].x += ux * force;
        disp[i].y += uy * force;
        disp[j].x -= ux * force;
        disp[j].y -= uy * force;
      }
    }

    // Attraction along edges.
    for (const edge of edges) {
      const a = indexOf.get(edge.source);
      const b = indexOf.get(edge.target);
      if (a == null || b == null || a === b) continue;
      let dx = pos[a].x - pos[b].x;
      let dy = pos[a].y - pos[b].y;
      const dist = Math.hypot(dx, dy) || 0.01;
      if (dist > width * 2.5) continue;
      const force = ((dist * dist) / k) * 0.55;
      const ux = dx / dist;
      const uy = dy / dist;
      disp[a].x -= ux * force;
      disp[a].y -= uy * force;
      disp[b].x += ux * force;
      disp[b].y += uy * force;
    }

    // Gravity toward the center + step.
    for (let i = 0; i < n; i += 1) {
      disp[i].x += (width / 2 - pos[i].x) * 0.035;
      disp[i].y += (height / 2 - pos[i].y) * 0.035;
      const len = Math.hypot(disp[i].x, disp[i].y) || 1;
      const stepSize = Math.min(len, temperature);
      pos[i].x += (disp[i].x / len) * stepSize;
      pos[i].y += (disp[i].y / len) * stepSize;
    }

    temperature *= 0.985;
  }

  // Separate the cards so they don't overlap.
  for (let pass = 0; pass < 50; pass += 1) {
    let moved = false;
    for (let i = 0; i < n; i += 1) {
      for (let j = i + 1; j < n; j += 1) {
        const wi = nodeWidth(nodes[i]);
        const wj = nodeWidth(nodes[j]);
        const minX = (wi + wj) / 2 + 26;
        const minY = NODE_HEIGHT + 20;
        const dx = pos[j].x - pos[i].x;
        const dy = pos[j].y - pos[i].y;
        const overlapX = minX - Math.abs(dx);
        const overlapY = minY - Math.abs(dy);
        if (overlapX <= 0 || overlapY <= 0) continue;
        moved = true;
        if (overlapX < overlapY) {
          const push = ((dx >= 0 ? 1 : -1) * overlapX) / 2;
          pos[j].x += push;
          pos[i].x -= push;
        } else {
          const push = ((dy >= 0 ? 1 : -1) * overlapY) / 2;
          pos[j].y += push;
          pos[i].y -= push;
        }
      }
    }
    if (!moved) break;
  }

  const minX = Math.min(...pos.map((p) => p.x));
  const minY = Math.min(...pos.map((p) => p.y));

  nodes.forEach((node, index) => {
    GRAPH.positions.set(node.id, {
      x: Math.round(pos[index].x - minX + 80),
      y: Math.round(pos[index].y - minY + 80),
    });
  });

  if (persist) scheduleSavePositions();
}

// ============================================================
// GRAPH: RENDERING
// ============================================================

function applyView() {
  const { view, els } = GRAPH;
  if (!els.world) return;
  els.world.style.transform =
    `translate(${view.x.toFixed(2)}px, ${view.y.toFixed(2)}px) scale(${view.k.toFixed(4)})`;
  if (GRAPH.popup) positionPopup();
}

function fitView() {
  const nodes = currentNodes();
  if (!nodes.length || !graphContainer.clientWidth) return;

  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;

  for (const node of nodes) {
    const pos = GRAPH.positions.get(node.id);
    if (!pos) continue;
    minX = Math.min(minX, pos.x);
    minY = Math.min(minY, pos.y);
    maxX = Math.max(maxX, pos.x + nodeWidth(node));
    maxY = Math.max(maxY, pos.y + NODE_HEIGHT);
  }
  if (!Number.isFinite(minX)) return;

  const rect = graphContainer.getBoundingClientRect();
  const pad = 46;
  const boxWidth = Math.max(maxX - minX, 1);
  const boxHeight = Math.max(maxY - minY, 1);

  let scale = Math.min(
    1.15,
    (rect.width - pad * 2) / boxWidth,
    (rect.height - pad * 2) / boxHeight,
  );
  scale = clamp(scale, 0.22, 1.3);

  GRAPH.view.k = scale;
  GRAPH.view.x = (rect.width - boxWidth * scale) / 2 - minX * scale;
  GRAPH.view.y = (rect.height - boxHeight * scale) / 2 - minY * scale;
  applyView();
}

function buildLegend() {
  const legend = el('div', 'graph__legend');
  const rows = [
    ['graph__legend-line', tr('сильная связь')],
    ['graph__legend-line graph__legend-line--medium', tr('средняя')],
    ['graph__legend-line graph__legend-line--low', tr('слабая')],
  ];
  for (const [className, label] of rows) {
    const row = el('div', 'graph__legend-row');
    row.appendChild(el('span', className));
    row.appendChild(el('span', null, label));
    legend.appendChild(row);
  }
  return legend;
}

function renderGraph(options = {}) {
  closeGraphPopup();
  graphContainer.replaceChildren();
  GRAPH.els.nodes.clear();
  GRAPH.els.edges.clear();
  GRAPH.els.edgeMid.clear();
  GRAPH.els.world = null;
  GRAPH.els.svg = null;
  GRAPH.els.nodeLayer = null;

  if (!INV.current) {
    graphCard.hidden = true;
    return;
  }

  graphCard.hidden = false;

  const nodes = currentNodes();
  const edges = currentEdges();
  graphNodesCount.textContent = String(nodes.length);
  graphEdgesCount.textContent = tf('{count} связей', { count: edges.length });

  if (!nodes.length) {
    const empty = el('div', 'graph__empty');
    empty.appendChild(el('div', null, tr('Граф пуст')));
    empty.appendChild(el('div', null, tr('Нажми «＋ Звено», чтобы добавить первое звено.')));
    graphContainer.appendChild(empty);
    return;
  }

  ensureGraphPositions(nodes);
  if (GRAPH.needsLayout) {
    GRAPH.needsLayout = false;
    runLayout(false);
  }

  const viewport = el('div', 'graph__viewport');
  const world = el('div', 'graph__world');
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('class', 'graph__edges');
  svg.setAttribute('width', '8000');
  svg.setAttribute('height', '8000');
  const nodeLayer = el('div', 'graph__nodes');

  world.appendChild(svg);
  world.appendChild(nodeLayer);
  viewport.appendChild(world);
  graphContainer.appendChild(viewport);
  graphContainer.appendChild(buildLegend());

  GRAPH.els.world = world;
  GRAPH.els.svg = svg;
  GRAPH.els.nodeLayer = nodeLayer;

  for (const node of nodes) {
    buildNodeEl(node);
  }
  for (const edge of edges) {
    buildEdgeEl(edge);
  }

  applyView();
  if (options.fit) {
    fitView();
  } else if (GRAPH.popup) {
    positionPopup();
  }
}

function buildNodeEl(node) {
  const pos = GRAPH.positions.get(node.id);
  if (!pos) return;

  const style = nodeStyle(node.type);
  const width = nodeWidth(node);

  const card = el('div', 'gnode');
  card.dataset.id = node.id;
  card.style.left = `${pos.x}px`;
  card.style.top = `${pos.y}px`;
  card.style.width = `${width}px`;
  card.style.height = `${NODE_HEIGHT}px`;
  card.style.setProperty('--node-bg', style.bg);
  card.style.setProperty('--node-border', style.border);
  if (node.type === 'center') card.classList.add('gnode--center');

  card.appendChild(el('span', 'gnode__num', node.num != null ? node.num : '•'));

  const body = el('div', 'gnode__body');
  body.appendChild(el('div', 'gnode__title', node.label || '?'));
  if (node.description) {
    body.appendChild(el('div', 'gnode__desc', node.description));
  }
  card.appendChild(body);

  const marks = [];
  if (node.url) marks.push('↗');
  if (node.notes) marks.push('✎');
  if (marks.length) {
    card.appendChild(el('span', 'gnode__mark', marks.join(' ')));
  }

  card.title = [
    node.label,
    node.description,
    node.url,
  ].filter(Boolean).join('\n');

  card.addEventListener('pointerdown', (event) => beginNodeDrag(event, node.id, card));
  card.addEventListener('click', (event) => event.stopPropagation());

  GRAPH.els.nodeLayer.appendChild(card);
  GRAPH.els.nodes.set(node.id, card);
}

function buildEdgeEl(edge) {
  const confidence = ['high', 'medium', 'low'].includes(edge.confidence)
    ? edge.confidence
    : 'medium';

  const group = document.createElementNS(SVG_NS, 'g');
  group.setAttribute('class', `gedge gedge--${confidence}`);
  group.dataset.id = edge.id;

  const hit = document.createElementNS(SVG_NS, 'path');
  hit.setAttribute('class', 'gedge__hit');

  const path = document.createElementNS(SVG_NS, 'path');
  path.setAttribute('class', 'gedge__path');

  const label = document.createElementNS(SVG_NS, 'text');
  label.setAttribute('class', 'gedge__label');
  label.textContent = edge.label || '';
  label.setAttribute('text-anchor', 'middle');

  group.appendChild(hit);
  group.appendChild(path);
  group.appendChild(label);

  group.addEventListener('pointerdown', (event) => event.stopPropagation());
  group.addEventListener('click', (event) => {
    event.stopPropagation();
    openEdgePopup(edge.id);
  });

  GRAPH.els.svg.appendChild(group);
  GRAPH.els.edges.set(edge.id, { group, hit, path, label });
  updateEdgeGeometry(edge);
}

function updateEdgeGeometry(edge) {
  const element = GRAPH.els.edges.get(edge.id);
  if (!element) return;
  const geometry = edgeGeometry(edge);
  if (!geometry) return;

  element.path.setAttribute('d', geometry.d);
  element.hit.setAttribute('d', geometry.d);
  element.label.setAttribute('x', geometry.mid.x.toFixed(2));
  element.label.setAttribute('y', (geometry.mid.y - 5).toFixed(2));
  GRAPH.els.edgeMid.set(edge.id, geometry.mid);
}

function updateIncidentEdges(nodeId) {
  for (const edge of currentEdges()) {
    if (edge.source === nodeId || edge.target === nodeId) {
      updateEdgeGeometry(edge);
    }
  }
}

// ============================================================
// GRAPH: DRAGGING / ZOOM / PANNING
// ============================================================

function beginNodeDrag(event, nodeId, card) {
  if (event.button !== 0) return;
  event.stopPropagation();

  const pos = GRAPH.positions.get(nodeId);
  if (!pos) return;

  GRAPH.drag = {
    id: nodeId,
    startClientX: event.clientX,
    startClientY: event.clientY,
    originX: pos.x,
    originY: pos.y,
    moved: false,
  };

  card.classList.add('is-dragging');
  try {
    card.setPointerCapture(event.pointerId);
  } catch {
    // ignore
  }
}

function moveNodeCard(nodeId) {
  const pos = GRAPH.positions.get(nodeId);
  const card = GRAPH.els.nodes.get(nodeId);
  if (!pos || !card) return;
  card.style.left = `${pos.x}px`;
  card.style.top = `${pos.y}px`;
}

function onWindowPointerMove(event) {
  if (GRAPH.drag) {
    const drag = GRAPH.drag;
    const dx = (event.clientX - drag.startClientX) / GRAPH.view.k;
    const dy = (event.clientY - drag.startClientY) / GRAPH.view.k;

    if (Math.hypot(dx, dy) > 3) drag.moved = true;

    GRAPH.positions.set(drag.id, {
      x: drag.originX + dx,
      y: drag.originY + dy,
    });
    moveNodeCard(drag.id);
    updateIncidentEdges(drag.id);
    if (GRAPH.popup && GRAPH.popup.kind === 'node' && GRAPH.popup.id === drag.id) {
      positionPopup();
    }
    return;
  }

  if (GRAPH.pan) {
    const dx = event.clientX - GRAPH.pan.startX;
    const dy = event.clientY - GRAPH.pan.startY;
    if (Math.hypot(dx, dy) > 3) GRAPH.pan.moved = true;
    GRAPH.view.x = GRAPH.pan.viewX + dx;
    GRAPH.view.y = GRAPH.pan.viewY + dy;
    applyView();
  }
}

function onWindowPointerUp() {
  if (GRAPH.drag) {
    const drag = GRAPH.drag;
    GRAPH.drag = null;
    const card = GRAPH.els.nodes.get(drag.id);
    if (card) card.classList.remove('is-dragging');

    if (drag.moved) {
      scheduleSavePositions();
    } else if (GRAPH.link) {
      handleNodeLinkClick(drag.id);
    } else {
      openNodePopup(drag.id);
    }
  }

  if (GRAPH.pan) {
    const wasClick = !GRAPH.pan.moved;
    GRAPH.pan = null;
    graphContainer.classList.remove('is-panning');
    if (wasClick) closeGraphPopup();
  }
}

function onGraphPointerDown(event) {
  if (event.button !== 0) return;
  if (event.target.closest('.gnode, .gpopup, .graph__legend')) return;

  GRAPH.pan = {
    startX: event.clientX,
    startY: event.clientY,
    viewX: GRAPH.view.x,
    viewY: GRAPH.view.y,
    moved: false,
  };
  graphContainer.classList.add('is-panning');
  try {
    graphContainer.setPointerCapture(event.pointerId);
  } catch {
    // ignore
  }
}

function onGraphWheel(event) {
  if (!INV.current) return;
  if (event.target.closest('.gpopup')) return;
  event.preventDefault();

  const rect = graphContainer.getBoundingClientRect();
  const mx = event.clientX - rect.left;
  const my = event.clientY - rect.top;

  const factor = Math.exp(-event.deltaY * 0.0012);
  const nextScale = clamp(GRAPH.view.k * factor, 0.18, 2.6);
  const ratio = nextScale / GRAPH.view.k;

  GRAPH.view.x = mx - (mx - GRAPH.view.x) * ratio;
  GRAPH.view.y = my - (my - GRAPH.view.y) * ratio;
  GRAPH.view.k = nextScale;
  applyView();
}

function scheduleSavePositions() {
  clearTimeout(GRAPH.saveTimer);
  GRAPH.saveTimer = setTimeout(async () => {
    if (!INV.current) return;
    const positions = {};
    for (const node of currentNodes()) {
      const pos = GRAPH.positions.get(node.id);
      if (pos) positions[node.id] = { x: pos.x, y: pos.y };
    }
    try {
      await apiJson(`/api/investigations/${INV.current.id}/positions`, {
        method: 'POST',
        body: { positions },
      });
    } catch (err) {
      console.warn('[positions]', err);
    }
  }, 700);
}

// ============================================================
// GRAPH: POPUPS
// ============================================================

function worldToScreen(x, y) {
  return {
    x: GRAPH.view.x + x * GRAPH.view.k,
    y: GRAPH.view.y + y * GRAPH.view.k,
  };
}

function closeGraphPopup() {
  if (GRAPH.popupEl) {
    GRAPH.popupEl.remove();
    GRAPH.popupEl = null;
  }
  if (GRAPH.popup && GRAPH.popup.kind === 'node') {
    const card = GRAPH.els.nodes.get(GRAPH.popup.id);
    if (card) card.classList.remove('is-active');
  }
  GRAPH.popup = null;
}

function positionPopup() {
  const popup = GRAPH.popupEl;
  if (!popup || !GRAPH.popup) return;

  let anchor = null;
  let anchorWidth = 0;

  if (GRAPH.popup.kind === 'node') {
    const node = getNodeById(GRAPH.popup.id);
    const pos = GRAPH.positions.get(GRAPH.popup.id);
    if (!node || !pos) return;
    anchor = worldToScreen(pos.x, pos.y);
    anchorWidth = nodeWidth(node) * GRAPH.view.k;
  } else {
    const mid = GRAPH.els.edgeMid.get(GRAPH.popup.id);
    if (!mid) return;
    anchor = worldToScreen(mid.x, mid.y);
  }

  const rect = graphContainer.getBoundingClientRect();
  const popupWidth = popup.offsetWidth || 318;
  const popupHeight = popup.offsetHeight || 240;
  const pad = 10;

  let left = anchor.x + anchorWidth + 14;
  if (left + popupWidth > rect.width - pad) {
    left = anchor.x - popupWidth - 14;
  }
  let top = anchor.y - 24;

  left = clamp(left, pad, Math.max(pad, rect.width - popupWidth - pad));
  top = clamp(top, pad, Math.max(pad, rect.height - popupHeight - pad));

  popup.style.left = `${Math.round(left)}px`;
  popup.style.top = `${Math.round(top)}px`;
}

function makePopupBase(kind, id) {
  closeGraphPopup();
  GRAPH.popup = { kind, id };

  const popup = el('div', 'gpopup');
  popup.addEventListener('pointerdown', (event) => event.stopPropagation());
  popup.addEventListener('click', (event) => event.stopPropagation());

  const close = el('button', 'gpopup__close', '×');
  close.type = 'button';
  close.title = tr('Закрыть');
  close.addEventListener('click', () => closeGraphPopup());
  popup.appendChild(close);

  GRAPH.popupEl = popup;
  graphContainer.appendChild(popup);
  return popup;
}

function popupHead(popup, number, titleText) {
  const head = el('div', 'gpopup__head');
  if (number != null) head.appendChild(el('span', 'gpopup__num', number));
  head.appendChild(el('div', 'gpopup__title', titleText));
  popup.appendChild(head);
}

function openNodePopup(nodeId) {
  const node = getNodeById(nodeId);
  if (!node) return;

  closeGraphPopup();
  const popup = makePopupBase('node', nodeId);
  popupHead(popup, node.num != null ? node.num : '•', node.label || '?');
  popup.appendChild(el('div', 'gpopup__type', TYPE_LABELS[node.type] || node.type || '?'));

  if (node.description) {
    popup.appendChild(el('div', 'gpopup__desc', node.description));
  }

  popup.appendChild(el('div', 'gpopup__label', tr('Источник')));

  if (node.url && safeHref(node.url)) {
    const link = el('a', 'gpopup__link', node.url);
    link.href = safeHref(node.url);
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    popup.appendChild(link);
  } else {
    popup.appendChild(el('span', 'gpopup__link gpopup__link--empty', tr('ссылка не указана')));
  }

  popup.appendChild(el('div', 'gpopup__label', tr('Заметка')));

  const notes = document.createElement('textarea');
  notes.className = 'gpopup__textarea';
  notes.rows = 3;
  notes.placeholder = tr('Что известно об этом звене…');
  notes.value = node.notes || '';
  popup.appendChild(notes);

  const status = el('span', 'gpopup__status', tr('✓ сохранено'));
  popup.appendChild(status);

  let notesTimer = null;
  const saveNotes = async () => {
    try {
      const data = await apiJson(
        `/api/investigations/${INV.current.id}/nodes/${node.id}`,
        { method: 'PATCH', body: { notes: notes.value } },
      );
      updateInvestigationFromResponse(data);
      node.notes = notes.value;
      status.classList.add('is-visible');
      clearTimeout(GRAPH.popupStatusTimer);
      GRAPH.popupStatusTimer = setTimeout(() => status.classList.remove('is-visible'), 1500);
      renderInvDetails();
    } catch (err) {
      showToast(tf('Не удалось сохранить заметку: {error}', { error: err.message }), { error: true });
    }
  };

  notes.addEventListener('input', () => {
    clearTimeout(notesTimer);
    notesTimer = setTimeout(saveNotes, 650);
  });
  notes.addEventListener('blur', () => {
    clearTimeout(notesTimer);
    saveNotes();
  });

  if (node.origin) {
    popup.appendChild(el('div', 'gpopup__label', tr('Откуда')));
    popup.appendChild(el('div', 'gpopup__desc', node.origin));
  }

  const actions = el('div', 'gpopup__actions');

  const linkBtn = el('button', 'btn btn--ghost', tr('🔗 Связать'));
  linkBtn.type = 'button';
  linkBtn.addEventListener('click', () => startLinkMode(node.id));
  actions.appendChild(linkBtn);

  const editBtn = el('button', 'btn btn--ghost', tr('✏ Изменить'));
  editBtn.type = 'button';
  editBtn.addEventListener('click', () => openNodeModal(node));
  actions.appendChild(editBtn);

  const deleteBtn = el('button', 'btn btn--ghost gpopup__danger', tr('🗑 Удалить'));
  deleteBtn.type = 'button';
  deleteBtn.addEventListener('click', () => deleteNode(node));
  actions.appendChild(deleteBtn);

  popup.appendChild(actions);
  positionPopup();

  const card = GRAPH.els.nodes.get(nodeId);
  if (card) card.classList.add('is-active');
}

function openEdgePopup(edgeId) {
  const edge = getEdgeById(edgeId);
  if (!edge) return;
  const a = getNodeById(edge.source);
  const b = getNodeById(edge.target);

  closeGraphPopup();
  const popup = makePopupBase('edge', edgeId);
  const head = el('div', 'gpopup__head');
  head.appendChild(el('div', 'gpopup__title', tr('Связь')));
  popup.appendChild(head);

  const pair = el('div', 'gpopup__pair');
  pair.appendChild(el('span', null, a ? a.label : '?'));
  pair.appendChild(el('span', 'gpopup__pair-arrow', '↕'));
  pair.appendChild(el('span', null, b ? b.label : '?'));
  popup.appendChild(pair);

  popup.appendChild(el('div', 'gpopup__label', tr('Подпись связи')));
  const labelInput = document.createElement('input');
  labelInput.className = 'gpopup__input';
  labelInput.value = edge.label || '';
  labelInput.maxLength = 200;
  popup.appendChild(labelInput);

  popup.appendChild(el('div', 'gpopup__label', tr('Уверенность')));
  const confidence = document.createElement('select');
  confidence.className = 'gpopup__select';
  for (const level of ['high', 'medium', 'low']) {
    const option = document.createElement('option');
    option.value = level;
    option.textContent = level === 'high' ? tr('высокая') : level === 'medium' ? tr('средняя') : tr('низкая');
    confidence.appendChild(option);
  }
  confidence.value = edge.confidence || 'medium';
  popup.appendChild(confidence);

  popup.appendChild(el('div', 'gpopup__label', tr('Заметка к связи')));
  const notes = document.createElement('textarea');
  notes.className = 'gpopup__textarea';
  notes.rows = 3;
  notes.placeholder = tr('Почему эти звенья связаны…');
  notes.value = edge.notes || '';
  popup.appendChild(notes);

  const status = el('span', 'gpopup__status', tr('✓ сохранено'));
  popup.appendChild(status);

  const saveEdge = async (fields) => {
    try {
      const data = await apiJson(
        `/api/investigations/${INV.current.id}/edges/${edge.id}`,
        { method: 'PATCH', body: fields },
      );
      updateInvestigationFromResponse(data);
      status.classList.add('is-visible');
      clearTimeout(GRAPH.popupStatusTimer);
      GRAPH.popupStatusTimer = setTimeout(() => status.classList.remove('is-visible'), 1500);
      renderInvDetails();
    } catch (err) {
      showToast(tf('Не удалось сохранить связь: {error}', { error: err.message }), { error: true });
    }
  };

  let notesTimer = null;
  notes.addEventListener('input', () => {
    clearTimeout(notesTimer);
    notesTimer = setTimeout(() => saveEdge({ notes: notes.value }), 650);
  });
  notes.addEventListener('blur', () => {
    clearTimeout(notesTimer);
    saveEdge({ notes: notes.value });
  });

  labelInput.addEventListener('change', () => {
    edge.label = labelInput.value;
    saveEdge({ label: labelInput.value });
    const element = GRAPH.els.edges.get(edge.id);
    if (element) element.label.textContent = labelInput.value;
  });

  confidence.addEventListener('change', () => {
    edge.confidence = confidence.value;
    saveEdge({ confidence: confidence.value });
    const element = GRAPH.els.edges.get(edge.id);
    if (element) {
      element.group.setAttribute('class', `gedge gedge--${confidence.value}`);
    }
  });

  if (edge.evidence) {
    popup.appendChild(el('div', 'gpopup__label', tr('Доказательство')));
    popup.appendChild(el('div', 'gpopup__desc', edge.evidence));
  }
  if (edge.reasoning) {
    popup.appendChild(el('div', 'gpopup__label', tr('Почему')));
    popup.appendChild(el('div', 'gpopup__desc', edge.reasoning));
  }
  if (edge.origin) {
    popup.appendChild(el('div', 'gpopup__label', tr('Откуда')));
    popup.appendChild(el('div', 'gpopup__desc', edge.origin));
  }

  const actions = el('div', 'gpopup__actions');
  const deleteBtn = el('button', 'btn btn--ghost gpopup__danger', tr('🗑 Удалить связь'));
  deleteBtn.type = 'button';
  deleteBtn.addEventListener('click', () => deleteEdge(edge));
  actions.appendChild(deleteBtn);
  popup.appendChild(actions);

  positionPopup();
}

// ============================================================
// GRAPH: LINK CREATION MODE
// ============================================================

function startLinkMode(sourceId = null) {
  if (!INV.current) {
    showToast(tr('Сначала создай расследование или добавь звено.'), { error: true });
    return;
  }
  if (currentNodes().length < 2) {
    showToast(tr('Нужно хотя бы два звена, чтобы создать связь.'), { error: true });
    return;
  }

  closeGraphPopup();
  GRAPH.link = { sourceId: sourceId || null };
  graphContainer.classList.add('is-linking');
  graphLinkHint.classList.remove('hidden');
  updateLinkModeHint();
}

function updateLinkModeHint() {
  for (const card of GRAPH.els.nodes.values()) {
    card.classList.remove('is-linksource');
  }

  const sourceId = GRAPH.link ? GRAPH.link.sourceId : null;
  if (sourceId) {
    const card = GRAPH.els.nodes.get(sourceId);
    if (card) card.classList.add('is-linksource');
    const node = getNodeById(sourceId);
    graphLinkHintText.textContent =
      tf('«{label}» выбран. Кликни по второму звену…', { label: node ? node.label : '?' });
  } else {
    graphLinkHintText.textContent = tr('Кликни по первому звену…');
  }
}

function cancelLinkMode() {
  GRAPH.link = null;
  graphContainer.classList.remove('is-linking');
  graphLinkHint.classList.add('hidden');
  for (const card of GRAPH.els.nodes.values()) {
    card.classList.remove('is-linksource');
  }
}

async function handleNodeLinkClick(nodeId) {
  if (!GRAPH.link) return;

  if (!GRAPH.link.sourceId) {
    GRAPH.link.sourceId = nodeId;
    updateLinkModeHint();
    return;
  }

  if (GRAPH.link.sourceId === nodeId) {
    cancelLinkMode();
    return;
  }

  const sourceId = GRAPH.link.sourceId;
  cancelLinkMode();

  try {
    const response = await apiJson(`/api/investigations/${INV.current.id}/edges`, {
      method: 'POST',
      body: {
        source: sourceId,
        target: nodeId,
        label: tr('связь'),
        confidence: 'high',
      },
    });
    updateInvestigationFromResponse(response);
    renderGraph();
    renderInvBar();
    renderInvDetails();
    showToast(response.created ? tr('Связь создана.') : tr('Такая связь уже была.'));
    openEdgePopup(response.edge.id);
  } catch (err) {
    showToast(tf('Не удалось создать связь: {error}', { error: err.message }), { error: true });
  }
}

// ============================================================
// NODE / EDGE ACTIONS
// ============================================================

async function deleteNode(node) {
  if (!INV.current) return;
  if (!window.confirm(tf('Удалить звено «{label}»? Связи с ним тоже удалятся.', { label: node.label }))) return;

  try {
    const response = await apiJson(
      `/api/investigations/${INV.current.id}/nodes/${node.id}`,
      { method: 'DELETE' },
    );
    updateInvestigationFromResponse(response);
    closeGraphPopup();
    renderGraph();
    renderInvBar();
    renderInvDetails();
    showToast(tr('Звено удалено.'));
  } catch (err) {
    showToast(tf('Не удалось удалить звено: {error}', { error: err.message }), { error: true });
  }
}

async function deleteEdge(edge) {
  if (!INV.current) return;
  if (!window.confirm(tr('Удалить эту связь?'))) return;

  try {
    const response = await apiJson(
      `/api/investigations/${INV.current.id}/edges/${edge.id}`,
      { method: 'DELETE' },
    );
    updateInvestigationFromResponse(response);
    closeGraphPopup();
    renderGraph();
    renderInvBar();
    renderInvDetails();
    showToast(tr('Связь удалена.'));
  } catch (err) {
    showToast(tf('Не удалось удалить связь: {error}', { error: err.message }), { error: true });
  }
}

// ============================================================
// NODE MODAL
// ============================================================

function openNodeModal(node = null) {
  if (!INV.current && !node) {
    // Take the position at the center of the current view.
    const rect = graphContainer.getBoundingClientRect();
    GRAPH.pendingNodePosition = {
      x: rect.width ? (rect.width / 2 - GRAPH.view.x) / GRAPH.view.k : 480,
      y: rect.height ? (rect.height / 2 - GRAPH.view.y) / GRAPH.view.k : 360,
    };
  } else {
    GRAPH.pendingNodePosition = null;
  }

  nodeModalTitle.textContent = node ? tr('Изменить звено') : tr('Новое звено');
  nodeIdInput.value = node ? node.id : '';
  nodeLabelInput.value = node ? node.label : '';
  nodeTypeInput.value = node ? (NODE_STYLES[node.type] ? node.type : 'custom') : 'custom';
  nodeNumInput.value = node && node.num != null ? node.num : '';
  nodeUrlInput.value = node ? (node.url || '') : '';
  nodeDescInput.value = node ? (node.description || '') : '';
  nodeNotesInput.value = node ? (node.notes || '') : '';

  nodeModal.classList.remove('hidden');
  setTimeout(() => nodeLabelInput.focus(), 30);
}

function closeNodeModal() {
  nodeModal.classList.add('hidden');
  nodeForm.reset();
  nodeIdInput.value = '';
}

async function ensureCurrentInvestigation() {
  if (INV.current) return INV.current;

  const selected = targetInvestigation.value;
  if (selected && selected !== '__new__') {
    const inv = await fetchInvestigation(selected);
    INV.current = inv;
    return inv;
  }

  const inv = await apiJson('/api/investigations', {
    method: 'POST',
    body: { title: tr('Новое расследование') },
  });
  INV.current = inv;
  await loadInvestigations();
  populateTargetSelect(inv.id);
  await updateLinkToField();
  return inv;
}

async function showGraphOnlyIfNeeded() {
  if (resultEl.classList.contains('hidden')) {
    resultEl.classList.remove('hidden');
    metaCard.hidden = true;
    summaryCard.hidden = true;
    thinkingCard.hidden = true;
    entitiesCard.hidden = true;
    connectionsCard.hidden = true;
    notesCard.hidden = true;
    treeCard.hidden = true;
    filterCard.hidden = true;
    rawCard.hidden = true;
  }
}

async function submitNodeForm(event) {
  event.preventDefault();

  const label = nodeLabelInput.value.trim();
  if (!label) {
    nodeLabelInput.focus();
    return;
  }

  try {
    const inv = await ensureCurrentInvestigation();
    const payload = {
      label,
      type: nodeTypeInput.value,
      url: nodeUrlInput.value.trim(),
      description: nodeDescInput.value.trim(),
      notes: nodeNotesInput.value.trim(),
    };

    const nodeId = nodeIdInput.value;
    let response;
    if (nodeId) {
      response = await apiJson(`/api/investigations/${inv.id}/nodes/${nodeId}`, {
        method: 'PATCH',
        body: payload,
      });
    } else {
      if (GRAPH.pendingNodePosition) {
        payload.x = GRAPH.pendingNodePosition.x;
        payload.y = GRAPH.pendingNodePosition.y;
      }
      response = await apiJson(`/api/investigations/${inv.id}/nodes`, {
        method: 'POST',
        body: payload,
      });
    }

    updateInvestigationFromResponse(response);
    closeNodeModal();
    await showGraphOnlyIfNeeded();
    renderGraph();
    renderInvBar();
    renderInvDetails();
    showToast(nodeId ? tr('Звено обновлено.') : tr('Звено добавлено в граф.'));
  } catch (err) {
    showToast(tf('Не удалось сохранить звено: {error}', { error: err.message }), { error: true });
  }
}

// ============================================================
// LLM SETTINGS
// ============================================================

const LLM_DEFAULTS = {
  ollama: {
    model: 'qwen2.5:7b',
    base: '',
  },
  openai: {
    model: 'gpt-4o-mini',
    base: 'https://api.openai.com/v1',
  },
  openrouter: {
    model: 'anthropic/claude-3.5-sonnet',
    base: 'https://openrouter.ai/api/v1',
  },
};

let currentLlmSettings = null;

function setLlmStatus(message, kind = '') {
  llmStatus.textContent = message || '';
  llmStatus.className = 'llm-status' + (kind ? ' is-' + kind : '');
}

function renderLlmStatus(status) {
  if (!status) {
    setLlmStatus('');
    return;
  }
  const label = status.provider_label || status.provider || 'LLM';
  const model = status.model || '—';
  if (status.ok) {
    setLlmStatus(tf('✓ {label} · {model} — доступна', { label, model }), 'ok');
  } else {
    setLlmStatus(tf('✗ {label} · {model} — {error}', { label, model, error: status.error || tr('недоступна') }), 'error');
  }
}

function updateLlmFields() {
  const provider = llmProvider.value;
  const isCloud = provider !== 'ollama';

  llmKeyField.classList.toggle('hidden', !isCloud);
  llmBaseField.classList.toggle('hidden', !isCloud);
  llmModelLabel.textContent = isCloud ? tr('Модель') : tr('Модель Ollama');

  if (isCloud && !llmBaseUrl.value.trim()) {
    llmBaseUrl.value = LLM_DEFAULTS[provider].base;
  }
}

function fillLlmForm(settings) {
  currentLlmSettings = settings;
  llmProvider.value = settings.provider || 'ollama';

  if (llmProvider.value === 'ollama') {
    llmModel.value = settings.ollama_model || settings.model || LLM_DEFAULTS.ollama.model;
  } else {
    llmModel.value = settings.openai_model || settings.model || LLM_DEFAULTS[llmProvider.value].model;
  }

  llmBaseUrl.value = settings.openai_base_url || '';
  llmApiKey.value = '';
  llmApiKey.placeholder = settings.has_api_key
    ? tf('Сохранён: {key}', { key: settings.api_key_masked })
    : 'sk-...';

  llmKeyHint.textContent = settings.has_api_key
    ? tf('Ключ уже сохранён ({key}). Оставьте поле пустым, чтобы не менять.', { key: settings.api_key_masked })
    : tr('Ключ не задан. Для облачного провайдера он обязателен.');

  updateLlmFields();
}

async function loadLlmSettings() {
  setLlmStatus(tr('Загрузка настроек…'), 'pending');
  try {
    const settings = await apiJson('/api/settings/llm');
    fillLlmForm(settings);
    setLlmStatus(tr('Нажмите «Проверить», чтобы протестировать сохранённые настройки.'), '');
  } catch (err) {
    setLlmStatus(tf('Не удалось загрузить настройки: {error}', { error: err.message }), 'error');
  }
}

function openLlmModal() {
  llmModal.classList.remove('hidden');
  loadLlmSettings();
}

function closeLlmModal() {
  llmModal.classList.add('hidden');
  llmApiKey.value = '';
}

async function saveLlmSettings(event) {
  event.preventDefault();

  const provider = llmProvider.value;
  const payload = {
    provider,
    model: llmModel.value.trim(),
  };
  if (provider !== 'ollama') {
    payload.base_url = llmBaseUrl.value.trim();
    payload.api_key = llmApiKey.value.trim();
  }

  setLlmStatus(tr('Сохранение…'), 'pending');
  try {
    const data = await apiJson('/api/settings/llm', {
      method: 'POST',
      body: payload,
    });
    fillLlmForm(data.settings);
    renderLlmStatus(data.status);
    await checkHealth();
    showToast(tr('Настройки LLM сохранены.'));
  } catch (err) {
    setLlmStatus(tf('Не удалось сохранить: {error}', { error: err.message }), 'error');
  }
}

async function testLlmSettings() {
  setLlmStatus(tr('Проверка подключения…'), 'pending');
  try {
    const status = await apiJson('/api/settings/llm/test', { method: 'POST' });
    renderLlmStatus(status);
  } catch (err) {
    setLlmStatus(tf('Ошибка проверки: {error}', { error: err.message }), 'error');
  }
}

function onLlmProviderChange() {
  const provider = llmProvider.value;
  const defaults = LLM_DEFAULTS[provider];

  if (provider === 'ollama') {
    llmModel.value = currentLlmSettings?.ollama_model || defaults.model;
    llmBaseUrl.value = '';
  } else {
    llmModel.value = defaults.model;
    llmBaseUrl.value = defaults.base;
  }
  updateLlmFields();
}

// ============================================================
// INVESTIGATIONS MODAL
// ============================================================

function openInvModal() {
  invModal.classList.remove('hidden');
  renderInvList();
  renderSavedPages();
}

function closeInvModal() {
  invModal.classList.add('hidden');
}

function renderInvList() {
  invListEl.replaceChildren();

  if (!INV.list.length) {
    invListEl.appendChild(el('div', 'inv-empty', tr('Пока нет расследований. Начни с поиска.')));
    return;
  }

  for (const item of INV.list) {
    const row = el('div', 'inv-item');
    if (INV.current && INV.current.id === item.id) row.classList.add('is-active');

    const main = el('div', 'inv-item__main');
    main.appendChild(el('div', 'inv-item__title', item.title || tr('Без названия')));
    main.appendChild(el(
      'div',
      'inv-item__meta',
      tf('{nodes} звеньев · {edges} связей · {searches} поисков · {date}', {
        nodes: item.node_count,
        edges: item.edge_count,
        searches: item.search_count,
        date: formatDate(item.updated_at),
      }),
    ));
    if (item.last_input) {
      main.appendChild(el('div', 'inv-item__meta', tf('последний запрос: {value}', { value: item.last_input })));
    }
    row.appendChild(main);

    const actions = el('div', 'inv-item__actions');

    const openBtn = el('button', 'btn btn--ghost btn--sm', tr('Открыть'));
    openBtn.type = 'button';
    openBtn.addEventListener('click', async () => {
      await loadInvestigation(item.id);
      closeInvModal();
    });
    actions.appendChild(openBtn);

    const deleteBtn = el('button', 'btn btn--ghost btn--sm gpopup__danger', '×');
    deleteBtn.type = 'button';
    deleteBtn.title = tr('Удалить расследование');
    deleteBtn.addEventListener('click', async () => {
      if (!window.confirm(tf('Удалить расследование «{title}»?', { title: item.title }))) return;
      try {
        await apiJson(`/api/investigations/${item.id}`, { method: 'DELETE' });
        if (INV.current && INV.current.id === item.id) {
          INV.current = null;
          GRAPH.positions.clear();
          resetResult();
        }
        INV.cache.delete(item.id);
        await loadInvestigations();
        populateTargetSelect();
        renderInvList();
        showToast(tr('Расследование удалено.'));
      } catch (err) {
        showToast(tf('Не удалось удалить: {error}', { error: err.message }), { error: true });
      }
    });
    actions.appendChild(deleteBtn);
    row.appendChild(actions);

    invListEl.appendChild(row);
  }
}

async function renderSavedPages() {
  savedPagesList.replaceChildren();
  savedPagesList.appendChild(el('div', 'inv-empty', tr('Загрузка…')));

  try {
    const data = await apiJson('/api/pages');
    const items = Array.isArray(data.items) ? data.items : [];
    savedPagesList.replaceChildren();

    if (!items.length) {
      savedPagesList.appendChild(el('div', 'inv-empty', tr('Сохранённых страниц пока нет.')));
      return;
    }

    for (const item of items) {
      const row = el('div', 'page-item');
      row.appendChild(el('div', 'page-item__name', item.filename));
      const meta = el('div', 'page-item__meta', tf('{size} КБ', { size: Math.round(item.size / 1024) }));
      row.appendChild(meta);

      const link = el('a', null, tr('Открыть'));
      link.href = item.url;
      link.target = '_blank';
      link.rel = 'noopener';
      row.appendChild(link);

      savedPagesList.appendChild(row);
    }
  } catch (err) {
    savedPagesList.replaceChildren(el('div', 'inv-empty', tf('Ошибка: {error}', { error: err.message })));
  }
}

async function loadInvestigation(id) {
  try {
    const inv = await fetchInvestigation(id);
    INV.current = inv;
    GRAPH.positions.clear();
    GRAPH.needsLayout = false;

    targetInvestigation.value = id;
    await updateLinkToField();

    resetResult();
    resultEl.classList.remove('hidden');
    metaCard.hidden = true;
    summaryCard.hidden = true;
    thinkingCard.hidden = true;
    entitiesCard.hidden = true;
    connectionsCard.hidden = true;
    notesCard.hidden = true;
    treeCard.hidden = true;
    filterCard.hidden = true;
    rawCard.hidden = true;

    renderInvBar();
    renderInvDetails();
    renderGraph({ fit: true });
    resultEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    showToast(tf('Открыто: {title}', { title: inv.title }));
  } catch (err) {
    showToast(tf('Не удалось открыть расследование: {error}', { error: err.message }), { error: true });
  }
}

async function createNewInvestigation() {
  const title = window.prompt(tr('Название расследования'), tr('Новое расследование'));
  if (title === null) return;

  try {
    const inv = await apiJson('/api/investigations', {
      method: 'POST',
      body: { title: title.trim() || tr('Новое расследование') },
    });
    INV.cache.set(inv.id, inv);
    INV.current = inv;
    await loadInvestigations();
    populateTargetSelect(inv.id);
    await updateLinkToField();
    closeInvModal();
    closeGraphPopup();
    GRAPH.positions.clear();
    resetResult();
    resultEl.classList.remove('hidden');
    metaCard.hidden = true;
    summaryCard.hidden = true;
    thinkingCard.hidden = true;
    entitiesCard.hidden = true;
    connectionsCard.hidden = true;
    notesCard.hidden = true;
    treeCard.hidden = true;
    filterCard.hidden = true;
    rawCard.hidden = true;
    renderInvBar();
    renderInvDetails();
    renderGraph({ fit: true });
    showToast(tr('Создано новое расследование.'));
  } catch (err) {
    showToast(tf('Не удалось создать расследование: {error}', { error: err.message }), { error: true });
  }
}

// ============================================================
// SAVING THE ANALYSIS PAGE AS HTML
// ============================================================

function computeGraphSnapshot(inv) {
  const nodes = Array.isArray(inv.nodes) ? inv.nodes : [];
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;

  for (const node of nodes) {
    const pos = GRAPH.positions.get(node.id) || {
      x: Number(node.x) || 0,
      y: Number(node.y) || 0,
    };
    minX = Math.min(minX, pos.x);
    minY = Math.min(minY, pos.y);
    maxX = Math.max(maxX, pos.x + nodeWidth(node));
    maxY = Math.max(maxY, pos.y + NODE_HEIGHT);
  }

  if (!Number.isFinite(minX)) {
    return { transform: 'translate(24px, 24px)', height: 320 };
  }

  const pad = 44;
  const boxWidth = Math.max(maxX - minX, 260);
  const boxHeight = Math.max(maxY - minY, 180);
  const scale = clamp(Math.min(1.15, (1080 - pad * 2) / boxWidth), 0.3, 1.15);
  const height = Math.round(boxHeight * scale + pad * 2);

  return {
    transform: `translate(${(pad - minX * scale).toFixed(2)}px, ${(pad - minY * scale).toFixed(2)}px) scale(${scale.toFixed(4)})`,
    height,
  };
}

async function downloadLogs() {
  downloadLogsBtn.disabled = true;
  try {
    const response = await fetch('/api/logs', { method: 'GET' });
    const text = await response.text();

    if (!response.ok) {
      throw new Error(text || `HTTP ${response.status}`);
    }

    const stamp = new Date().toISOString()
      .replace(/[-:]/g, '').replace('T', '_').slice(0, 15);
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `skyfall_logs_${stamp}.log`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 2000);
    showToast(tr('Лог-файл скачан.'));
  } catch (err) {
    showToast(tf('Не удалось скачать логи: {error}', { error: err.message }), { error: true });
  } finally {
    downloadLogsBtn.disabled = false;
  }
}

async function saveAnalysisPage() {
  if (!INV.current) {
    showToast(tr('Сначала проведи поиск или создай расследование.'), { error: true });
    return;
  }

  savePageBtn.disabled = true;
  try {
    const css = await fetch('/static/style.css').then((r) => (r.ok ? r.text() : ''));

    if (GRAPH.popup) closeGraphPopup();

    const clone = document.documentElement.cloneNode(true);

    clone.querySelectorAll('script').forEach((node) => node.remove());
    clone.querySelectorAll('link[rel="stylesheet"]').forEach((node) => node.remove());
    clone.querySelectorAll('.modal, .toast, .gpopup, .graph__legend, .graph__linkhint, .graph__toolbar, .inv-bar__actions, #openInvListBtn, #openLlmSettingsBtn, #downloadLogsBtn').forEach((node) => node.remove());

    // We don't show the search form, progress, or errors in the snapshot.
    const formCard = clone.querySelector('#investigate-form');
    if (formCard && formCard.closest('section')) {
      formCard.closest('section').remove();
    }
    clone.querySelectorAll('#progress, #error').forEach((node) => node.remove());

    // Hide everything unnecessary on the static page.
    const snapshotStyle = document.createElement('style');
    snapshotStyle.textContent = `
      .snapshot-banner {
        max-width: 960px; margin: 0 auto 0; padding: 12px 16px;
        background: rgba(63,185,80,.08); border: 1px solid rgba(63,185,80,.28);
        border-radius: 8px; color: #8b949e; font: 12px/1.6 ui-monospace, monospace;
      }
      .snapshot-banner strong { color: #3fb950; }
      .header { border-bottom-color: rgba(63,185,80,.35); }
      .inv-bar__title { pointer-events: none; }
      .graph { cursor: default; }
      .gnode { cursor: default; }
      .toast, .modal, .gpopup { display: none !important; }
    `;
    clone.querySelector('head').appendChild(snapshotStyle);

    const styleTag = document.createElement('style');
    styleTag.textContent = css;
    clone.querySelector('head').appendChild(styleTag);

    const title = INV.current.title || tr('Skyfall — анализ');
    const titleEl = clone.querySelector('title');
    if (titleEl) titleEl.textContent = `${title} — Skyfall`;

    const cloneTitleInput = clone.querySelector('#invTitle');
    if (cloneTitleInput) cloneTitleInput.setAttribute('value', title);

    const cloneDetails = clone.querySelector('#invDetailsCard');
    if (cloneDetails) cloneDetails.setAttribute('open', '');

    // Static graph snapshot: reset pan/zoom, fit to width.
    const snapshot = computeGraphSnapshot(INV.current);
    const cloneGraph = clone.querySelector('#graph');
    if (cloneGraph) {
      const world = cloneGraph.querySelector('.graph__world');
      if (world) {
        world.style.transform = snapshot.transform;
      }
      cloneGraph.style.height = `${snapshot.height}px`;
    }

    // Vertical coordinates and labels are kept in the cards' inline styles.

    const banner = document.createElement('div');
    banner.className = 'snapshot-banner';
    const strong = document.createElement('strong');
    strong.textContent = tr('Skyfall · сохранённая страница анализа');
    banner.appendChild(strong);
    banner.appendChild(document.createTextNode(
      ' — ' + tf('{title}, {date}. ', {
        title,
        date: formatDate(new Date().toISOString()),
      }) + tf('Звеньев: {nodes}, связей: {edges}.', {
        nodes: currentNodes().length,
        edges: currentEdges().length,
      }),
    ));

    const main = clone.querySelector('main');
    if (main) main.insertBefore(banner, main.firstChild);

    const html = '<!DOCTYPE html>\n' + clone.outerHTML;

    const saved = await apiJson(`/api/investigations/${INV.current.id}/save-page`, {
      method: 'POST',
      body: { html, title },
    });

    invSaved.classList.remove('hidden');
    invSaved.replaceChildren();
    invSaved.appendChild(document.createTextNode(tf('Сохранено в {path} · ', { path: saved.path })));
    const openLink = el('a', null, tr('открыть страницу'));
    openLink.href = saved.url;
    openLink.target = '_blank';
    openLink.rel = 'noopener';
    invSaved.appendChild(openLink);

    showToast(tf('Страница сохранена: {name}', { name: saved.filename }), {
      href: saved.url,
      linkLabel: tr('Открыть'),
      timeout: 12000,
    });
  } catch (err) {
    showToast(tf('Не удалось сохранить страницу: {error}', { error: err.message }), { error: true });
  } finally {
    savePageBtn.disabled = false;
  }
}

// ============================================================
// RESET AND MAIN RENDER
// ============================================================

function resetResult() {
  resultEl.classList.add('hidden');
  summaryCard.hidden = true;
  thinkingCard.hidden = true;
  entitiesCard.hidden = true;
  connectionsCard.hidden = true;
  notesCard.hidden = true;
  treeCard.hidden = true;
  filterCard.hidden = true;
  droppedBlock.hidden = true;
  filterThinkingWrap.hidden = true;
  contradictionsCol.hidden = true;
  uncertaintiesCol.hidden = true;
  invBar.classList.add('hidden');
  invDetailsCard.hidden = true;
  metaCard.hidden = false;
  rawCard.hidden = false;

  entitiesList.replaceChildren();
  connectionsList.replaceChildren();
  contradictionsList.replaceChildren();
  uncertaintiesList.replaceChildren();
  treeRoot.replaceChildren();
  keptList.replaceChildren();
  droppedList.replaceChildren();
  invSearches.replaceChildren();
  invDetails.replaceChildren();

  cancelLinkMode();
  closeGraphPopup();
  closeNodeModal();
  graphCard.hidden = true;
  graphContainer.replaceChildren();
  GRAPH.els.nodes.clear();
  GRAPH.els.edges.clear();
  GRAPH.els.edgeMid.clear();
  GRAPH.els.world = null;
  GRAPH.els.svg = null;
  GRAPH.els.nodeLayer = null;
  invSaved.classList.add('hidden');
  invSaved.replaceChildren();

  metaMode.textContent = '—';
  metaMode.className = 'mode-badge';
}

function setModeBadge(mode) {
  const labels = {
    ai: 'AI',
    raw: 'Raw Mode',
    raw_fallback: 'Raw fallback',
    no_data: tr('Нет данных'),
  };
  labels.ai = tr('AI');
  labels.raw = tr('Raw Mode');
  labels.raw_fallback = tr('Raw fallback');
  metaMode.textContent = labels[mode] || String(mode || '—');
  metaMode.className = 'mode-badge mode-badge--' + String(mode || 'unknown');
}

function renderResult(data) {
  resetResult();

  metaInput.textContent = data.input || '—';
  metaType.textContent  = data.input_type || '—';
  metaTime.textContent  = formatDate(data.collected_at);
  metaPath.textContent  = data.report_path || '—';

  const analysis = data.analysis && typeof data.analysis === 'object'
    ? data.analysis
    : {};

  const mode = data.mode || analysis.mode
    || (data.ai_used === false ? 'raw' : 'ai');
  setModeBadge(mode);

  if (analysis.error) {
    showError(tf('Ошибка анализа: {error}', { error: analysis.error }));
  }

  if (mode === 'raw_fallback' && analysis.notice) {
    showToast(tf('AI недоступен: {notice}', { notice: analysis.notice }), { error: true, timeout: 9000 });
  }

  renderSummary(analysis);
  renderThinking(analysis);
  renderEntities(analysis);
  renderConnections(analysis);
  renderNotes(analysis);
  renderTree(analysis);
  renderFilter(data.filtered);
  renderRaw(data.raw_data);

  resultEl.classList.remove('hidden');

  if (INV.current) {
    renderInvBar();
    renderInvDetails();
    renderGraph({ fit: true });
  }

  resultEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ============================================================
// FORM SUBMISSION (SEARCH + IMPORT INTO INVESTIGATION)
// ============================================================

async function removeIfEmpty(invId) {
  try {
    const inv = await apiJson(`/api/investigations/${invId}`);
    if (!inv.nodes || !inv.nodes.length) {
      await apiJson(`/api/investigations/${invId}`, { method: 'DELETE' });
    }
  } catch {
    // ignore
  }
  await loadInvestigations();
  populateTargetSelect();
}

const PROGRESS_COPY = {
  username: {
    title: tr('Идёт поиск по нику…'),
    ai: tr('Sherlock и Maigret проверяют тысячи сайтов. AI-этапы могут занять несколько минут; '
      + 'если LLM недоступна или не уложилась в таймаут, Skyfall покажет сырые данные.'),
    raw: tr('Sherlock и Maigret проверяют тысячи сайтов. AI отключён: будут показаны сырые профили.'),
  },
  email: {
    title: tr('Идёт поиск по email…'),
    ai: tr('Holehe проверяет, где зарегистрирован email. Если Holehe не найдёт сайтов, запустится '
      + 'Diablinda. Затем LLM фильтрует и анализирует результаты.'),
    raw: tr('Holehe проверяет, где зарегистрирован email. Если Holehe не найдёт сайтов, запустится '
      + 'Diablinda. AI отключён: будут показаны сырые данные.'),
  },
  domain: {
    title: tr('Идёт анализ домена…'),
    ai: tr('theHarvester собирает emails, субдомены и хосты, ThreatFox проверяет IOC. '
      + 'Затем LLM фильтрует и анализирует данные.'),
    raw: tr('theHarvester собирает emails, субдомены и хосты, ThreatFox проверяет IOC. '
      + 'AI отключён: будут показаны сырые данные.'),
  },
};

function updateProgressCopy(inputType, useAI) {
  const copy = PROGRESS_COPY[inputType] || PROGRESS_COPY.username;
  progressTitle.textContent = copy.title;
  progressHint.textContent = useAI ? copy.ai : copy.raw;
}

async function submitInvestigation(event) {
  event.preventDefault();

  const inputType = form.querySelector('input[name="input_type"]:checked')?.value || 'username';
  const value = valueInput.value.trim();

  if (!value) {
    showError(tr('Введи значение для поиска.'));
    valueInput.focus();
    return;
  }

  hideError();
  resetResult();
  setLoading(true);
  updateProgressCopy(inputType, !rawModeCheckbox.checked);
  showProgress(true);

  let activeId = targetInvestigation.value;
  let createdNew = false;

  try {
    // 1. Target investigation: new or existing.
    if (!activeId || activeId === '__new__') {
      const inv = await apiJson('/api/investigations', {
        method: 'POST',
        body: { title: value },
      });
      activeId = inv.id;
      createdNew = true;
      INV.cache.set(inv.id, inv);
      await loadInvestigations();
    }

    // 2. The search itself.
    const data = await apiJson('/api/investigate', {
      method: 'POST',
      body: {
        input_type: inputType,
        value,
        language: 'ru',
        use_ai: !rawModeCheckbox.checked,
      },
    });

    const hasAnalysis = data.analysis
      && typeof data.analysis === 'object'
      && Object.keys(data.analysis).length > 0;

    if (data.error && !hasAnalysis) {
      showError(data.error);
      if (createdNew) await removeIfEmpty(activeId);
      return;
    }

    // 3. Import the result into the investigation graph.
    let stats = null;
    try {
      const linkTo = linkToNode.value || null;
      const imported = await apiJson(`/api/investigations/${activeId}/import`, {
        method: 'POST',
        body: { result: data, link_to: linkTo },
      });
      updateInvestigationFromResponse(imported);
      stats = imported.stats;
    } catch (importError) {
      console.warn('[import]', importError);
      showToast(tf('Поиск выполнен, но в граф не добавлен: {error}', { error: importError.message }), { error: true });
    }

    if (!INV.current || INV.current.id !== activeId) {
      try {
        INV.current = await apiJson(`/api/investigations/${activeId}`);
      } catch {
        INV.current = null;
      }
    }

    await loadInvestigations();
    populateTargetSelect(activeId);
    await updateLinkToField();

    renderResult(data);

    if (stats) {
      const parts = [tf('+{count} звеньев', { count: stats.nodes_added }), tf('+{count} связей', { count: stats.edges_added })];
      showToast(tf('В граф расследования добавлено: {parts}.', { parts: parts.join(', ') }));
    }
  } catch (err) {
    console.error('[submitInvestigation]', err);
    showError(err.message || tr('Неизвестная ошибка'));
    if (createdNew) await removeIfEmpty(activeId);
  } finally {
    showProgress(false);
    setLoading(false);
  }
}

// ============================================================
// UPDATING LABELS WHEN THE TYPE CHANGES
// ============================================================

const TYPE_HINTS = {
  username: {
    label: tr('Ник'),
    placeholder: tr('Например: octocat'),
    hint: tr('Введи ник, который хочешь проверить.'),
  },
  email: {
    label: tr('Email'),
    placeholder: tr('Например: user@example.com'),
    hint: tr('Проверим, где зарегистрирован этот email (Holehe).'),
  },
  domain: {
    label: tr('Домен'),
    placeholder: tr('Например: example.com'),
    hint: tr('Соберём emails и субдомены через theHarvester.'),
  },
};

function updateTypeUI() {
  const inputType = form.querySelector('input[name="input_type"]:checked')?.value || 'username';
  const conf = TYPE_HINTS[inputType] || TYPE_HINTS.username;

  valueLabel.textContent = conf.label;
  valueInput.placeholder = conf.placeholder;
  valueInput.value = '';
  valueHint.textContent = conf.hint;
  updateProgressCopy(inputType, !rawModeCheckbox.checked);
  valueInput.focus();
}

// ============================================================
// INITIALIZATION
// ============================================================

function initGraphInteractions() {
  graphContainer.addEventListener('pointerdown', onGraphPointerDown);
  graphContainer.addEventListener('wheel', onGraphWheel, { passive: false });
  window.addEventListener('pointermove', onWindowPointerMove);
  window.addEventListener('pointerup', onWindowPointerUp);
  window.addEventListener('pointercancel', onWindowPointerUp);

  graphContainer.addEventListener('click', (event) => {
    if (event.target.closest('.gnode, .gpopup, .gedge')) return;
    closeGraphPopup();
  });
}

function init() {
  initGraphInteractions();

  form.addEventListener('submit', submitInvestigation);
  form.querySelectorAll('input[name="input_type"]').forEach((radio) => {
    radio.addEventListener('change', updateTypeUI);
  });

  targetInvestigation.addEventListener('change', async () => {
    const selected = targetInvestigation.value;
    if (selected && selected !== '__new__'
        && (!INV.current || INV.current.id !== selected)) {
      await loadInvestigation(selected);
      return;
    }
    await updateLinkToField();
  });

  invTitle.addEventListener('change', async () => {
    if (!INV.current) return;
    const title = invTitle.value.trim();
    if (!title || title === INV.current.title) {
      invTitle.value = INV.current.title || '';
      return;
    }
    try {
      const inv = await apiJson(`/api/investigations/${INV.current.id}`, {
        method: 'PATCH',
        body: { title },
      });
      INV.current = inv;
      INV.cache.set(inv.id, inv);
      await loadInvestigations();
      populateTargetSelect(inv.id);
      renderInvBar();
      showToast(tr('Название обновлено.'));
    } catch (err) {
      showToast(tf('Не удалось переименовать: {error}', { error: err.message }), { error: true });
      invTitle.value = INV.current.title || '';
    }
  });

  invTitle.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      invTitle.blur();
    }
  });

  savePageBtn.addEventListener('click', saveAnalysisPage);
  downloadLogsBtn.addEventListener('click', downloadLogs);

  if (localStorage.getItem('skyfall.rawMode') === '1') {
    rawModeCheckbox.checked = true;
  }
  rawModeCheckbox.addEventListener('change', () => {
    localStorage.setItem('skyfall.rawMode', rawModeCheckbox.checked ? '1' : '0');
  });

  addNodeBtn.addEventListener('click', () => openNodeModal(null));
  linkModeBtn.addEventListener('click', () => startLinkMode(null));
  cancelLinkBtn.addEventListener('click', cancelLinkMode);

  relayoutBtn.addEventListener('click', () => {
    if (!INV.current) return;
    runLayout(false);
    renderGraph({ fit: true });
    scheduleSavePositions();
    showToast(tr('Граф разложен заново.'));
  });

  fitGraphBtn.addEventListener('click', fitView);

  nodeForm.addEventListener('submit', submitNodeForm);

  document.querySelectorAll('[data-close-node-modal]').forEach((node) => {
    node.addEventListener('click', closeNodeModal);
  });

  openInvListBtn.addEventListener('click', openInvModal);
  newInvBtn.addEventListener('click', createNewInvestigation);
  document.querySelectorAll('[data-close-inv-modal]').forEach((node) => {
    node.addEventListener('click', closeInvModal);
  });

  openLlmSettingsBtn.addEventListener('click', openLlmModal);
  llmForm.addEventListener('submit', saveLlmSettings);
  llmTestBtn.addEventListener('click', testLlmSettings);
  llmProvider.addEventListener('change', onLlmProviderChange);
  document.querySelectorAll('[data-close-llm-modal]').forEach((node) => {
    node.addEventListener('click', closeLlmModal);
  });

  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    if (!nodeModal.classList.contains('hidden')) {
      closeNodeModal();
      return;
    }
    if (!invModal.classList.contains('hidden')) {
      closeInvModal();
      return;
    }
    if (!llmModal.classList.contains('hidden')) {
      closeLlmModal();
      return;
    }
    if (GRAPH.link) {
      cancelLinkMode();
      return;
    }
    closeGraphPopup();
  });

  checkHealth();

  (async () => {
    await loadInvestigations();

    const params = new URLSearchParams(window.location.search);
    const invId = params.get('investigation');
    if (invId) {
      await loadInvestigation(invId);
    } else {
      await updateLinkToField();
    }
  })();
}

init();
