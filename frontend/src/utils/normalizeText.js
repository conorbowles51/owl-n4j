import anyAscii from 'any-ascii';

export function normalizeForSearch(str) {
  if (!str) return '';
  return anyAscii(str).toLowerCase();
}
