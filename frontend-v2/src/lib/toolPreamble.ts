/** Matches backend tool-only placeholder text — hide from chat streaming. */

const PREAMBLE_EXACT = new Set([
  'Reading workspace file…',
  'Reading workspace file...',
  'Searching the web…',
  'Searching the web...',
  'Fetching page content…',
  'Loading rendered page content…',
  'Running deep research…',
  'Writing to workspace…',
])

const PREAMBLE_PREFIX = [
  /^Reading workspace file/i,
  /^Searching the web/i,
  /^Fetching page content/i,
  /^Loading rendered page content/i,
  /^Running deep research/i,
  /^Writing to workspace/i,
  /^Running \*\*.+\*\*…$/,
  /^Working on your request/i,
]

export function isToolPreambleText(text: string): boolean {
  const cleaned = text.trim()
  if (!cleaned) return true
  if (PREAMBLE_EXACT.has(cleaned)) return true
  return PREAMBLE_PREFIX.some((re) => re.test(cleaned))
}
