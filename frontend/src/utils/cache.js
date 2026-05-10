// Module-level cache — persists across React route changes (not page refreshes)
// Keys are API endpoint paths, values are { data, ts }
const store = {};

export function getCache(key) {
  return store[key]?.data ?? null;
}

export function setCache(key, data) {
  store[key] = { data, ts: Date.now() };
}

export function isFresh(key, ttlMs = 30000) {
  return !!(store[key] && Date.now() - store[key].ts < ttlMs);
}

export function clearCache(key) {
  delete store[key];
}
