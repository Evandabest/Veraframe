/**
 * Tiny parser for the multi-segment "Script" prompt mode.
 *
 * Users author a list of timestamped prompts, one per line:
 *
 *     @0    alice walks to the door
 *     @4    alice waves at bob
 *     @6-10 they argue
 *
 * Each line is parsed into a {start, end, prompt} segment. The end is
 * optional — when omitted it's filled in from the next segment's start
 * (or left null for the trailing line). Comments (`#`) and blank lines
 * are ignored.
 *
 * The compiled output is a single structured prompt the existing LLM
 * pipeline can consume. We append explicit timing per segment so the
 * model knows to honor those windows when it emits the timeline.
 */

export interface ScriptSegment {
  /** Start time in seconds (parsed from `@<time>` prefix). */
  start: number
  /** End time in seconds. Null when the line had no explicit end and there
   *  is no following segment to backfill from. */
  end: number | null
  /** Natural-language description of what should happen in this window. */
  prompt: string
  /** 1-indexed source line number for error reporting. */
  line: number
}

export interface ScriptParseError {
  line: number
  message: string
  /** The offending raw text. */
  raw: string
}

export interface ScriptParseResult {
  segments: ScriptSegment[]
  errors: ScriptParseError[]
}

const LINE_PATTERN = /^@\s*(\d+(?:\.\d+)?)\s*(?:-\s*(\d+(?:\.\d+)?)\s*)?(.*)$/

export function parseScript(raw: string): ScriptParseResult {
  const segments: ScriptSegment[] = []
  const errors: ScriptParseError[] = []

  const lines = raw.split('\n')
  for (let i = 0; i < lines.length; i += 1) {
    const rawLine = lines[i]
    const trimmed = rawLine.trim()
    if (trimmed === '' || trimmed.startsWith('#')) continue
    if (!trimmed.startsWith('@')) {
      errors.push({
        line: i + 1,
        message: 'script lines must start with @<time> (e.g. "@0 alice walks")',
        raw: rawLine
      })
      continue
    }
    const match = LINE_PATTERN.exec(trimmed)
    if (!match) {
      errors.push({
        line: i + 1,
        message: 'could not parse @<time> prefix',
        raw: rawLine
      })
      continue
    }
    const start = Number(match[1])
    const end = match[2] != null ? Number(match[2]) : null
    const prompt = match[3].trim()
    if (prompt === '') {
      errors.push({ line: i + 1, message: 'empty prompt after timestamp', raw: rawLine })
      continue
    }
    if (end !== null && end <= start) {
      errors.push({
        line: i + 1,
        message: `end (${end}) must be greater than start (${start})`,
        raw: rawLine
      })
      continue
    }
    segments.push({ start, end, prompt, line: i + 1 })
  }

  // Backfill missing ends from the next segment's start. The last segment
  // keeps end=null when it had no explicit range; the LLM picks a sensible
  // duration for the tail.
  for (let i = 0; i < segments.length - 1; i += 1) {
    if (segments[i].end === null) {
      const next = segments[i + 1].start
      if (next > segments[i].start) segments[i].end = next
    }
  }

  // Sanity: segments must be non-overlapping and monotonic.
  for (let i = 0; i < segments.length - 1; i += 1) {
    const a = segments[i]
    const b = segments[i + 1]
    if (b.start < a.start) {
      errors.push({
        line: b.line,
        message: `segment starts at ${b.start}s but the previous segment starts at ${a.start}s`,
        raw: ''
      })
    }
    if (a.end !== null && b.start < a.end) {
      errors.push({
        line: b.line,
        message: `segment overlaps the previous one ending at ${a.end}s`,
        raw: ''
      })
    }
  }

  return { segments, errors }
}

/**
 * Compile a script (already parsed) into a single structured prompt for
 * the existing single-shot LLM pipeline. The model is told to honor the
 * explicit time windows; segments with no end are described as "until the
 * next segment" or "to the end" for the tail.
 */
export function compileScriptToPrompt(segments: ScriptSegment[]): string {
  if (segments.length === 0) return ''
  const lines: string[] = [
    '# Timed script',
    'Produce a timeline whose actions honor these exact time windows. Each',
    'numbered segment describes what should happen in that window — choose',
    'the action types and parameters that best match the description.',
    ''
  ]
  for (let i = 0; i < segments.length; i += 1) {
    const s = segments[i]
    const end =
      s.end !== null
        ? `${s.end}s`
        : i < segments.length - 1
          ? `${segments[i + 1].start}s`
          : 'end of video'
    lines.push(`${i + 1}. ${s.start}s–${end}: ${s.prompt}`)
  }
  return lines.join('\n')
}
