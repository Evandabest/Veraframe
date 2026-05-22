/**
 * ffmpeg helpers for incremental video rendering.
 *
 * - `splice` replaces a time window inside an existing MP4 with a new slice.
 *   Used when the user edits an existing block: we render only the frames
 *   inside the edited block in Blender, then splice them into the previous
 *   video. Uses the `concat` filter (re-encodes) because copy-concat would
 *   require keyframes at the cut points, which we can't guarantee.
 *
 * - `append` concatenates a new tail onto the end of an existing MP4. Used
 *   for timeline extensions where the new content sits past the previous
 *   video's end. Tries `-c copy` first (no re-encode) and falls back to a
 *   filter-based concat if codec/dimension mismatches make copy unsafe.
 *
 * Both spawn the system `ffmpeg` binary (~/.local, /opt/homebrew, etc.).
 * Missing ffmpeg surfaces as a clear error from `child.once('error')`.
 */

import { spawn } from 'child_process'
import { randomUUID } from 'crypto'
import { writeFile, unlink } from 'fs/promises'
import { tmpdir } from 'os'
import { join } from 'path'

class FfmpegError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'FfmpegError'
  }
}

function runFfmpeg(args: string[]): Promise<void> {
  return new Promise((resolve, reject) => {
    const child = spawn('ffmpeg', args, { stdio: ['ignore', 'pipe', 'pipe'] })
    let stderr = ''
    child.stderr.on('data', (chunk) => {
      stderr += chunk.toString('utf8')
    })
    child.once('error', (err) => {
      reject(new FfmpegError(`ffmpeg spawn failed: ${err.message}`))
    })
    child.once('close', (code) => {
      if (code === 0) {
        resolve()
      } else {
        // Surface only the tail of stderr so the error stays readable.
        const tail = stderr.split('\n').slice(-12).join('\n').trim()
        reject(new FfmpegError(`ffmpeg exited with code ${code}: ${tail}`))
      }
    })
  })
}

/**
 * Replace the time window [startSec, endSec] in `previousPath` with the
 * contents of `slicePath`, writing the spliced result to `outputPath`. The
 * slice is assumed to cover exactly (endSec - startSec) seconds of content;
 * Blender's daemon render call produces this when given matching start/end
 * frames.
 */
export async function ffmpegSplice(
  previousPath: string,
  slicePath: string,
  startSec: number,
  endSec: number,
  outputPath: string
): Promise<void> {
  // The concat filter takes three trims: previous[0..start], the slice, and
  // previous[end..]. setpts=PTS-STARTPTS resets each segment's timestamps so
  // concat can stitch them sequentially.
  await runFfmpeg([
    '-y',
    '-i',
    previousPath,
    '-i',
    slicePath,
    '-filter_complex',
    [
      `[0:v]trim=0:${startSec},setpts=PTS-STARTPTS[a]`,
      `[1:v]setpts=PTS-STARTPTS[b]`,
      `[0:v]trim=${endSec},setpts=PTS-STARTPTS[c]`,
      `[a][b][c]concat=n=3:v=1[out]`
    ].join(';'),
    '-map',
    '[out]',
    '-c:v',
    'libx264',
    '-preset',
    'fast',
    '-crf',
    '18',
    '-pix_fmt',
    'yuv420p',
    outputPath
  ])
}

/**
 * Append `slicePath` to the end of `previousPath`, writing the result to
 * `outputPath`. Tries the concat demuxer with `-c copy` first (instant,
 * no re-encode); falls back to a filter-based re-encode if copy fails
 * (codec/dimension mismatch, etc.).
 */
export async function ffmpegAppend(
  previousPath: string,
  slicePath: string,
  outputPath: string
): Promise<void> {
  const listPath = join(tmpdir(), `veraframe-concat-${randomUUID()}.txt`)
  // The concat demuxer reads a file with `file '<absolute path>'` lines.
  // Single quotes around the paths so spaces are safe.
  await writeFile(listPath, `file '${previousPath}'\nfile '${slicePath}'\n`, 'utf8')
  try {
    await runFfmpeg([
      '-y',
      '-f',
      'concat',
      '-safe',
      '0',
      '-i',
      listPath,
      '-c',
      'copy',
      outputPath
    ])
  } catch {
    // Copy-concat failed (probably codec/dimension mismatch); fall back to
    // a filter-based re-encode which always works.
    await runFfmpeg([
      '-y',
      '-i',
      previousPath,
      '-i',
      slicePath,
      '-filter_complex',
      '[0:v][1:v]concat=n=2:v=1[out]',
      '-map',
      '[out]',
      '-c:v',
      'libx264',
      '-preset',
      'fast',
      '-crf',
      '18',
      '-pix_fmt',
      'yuv420p',
      outputPath
    ])
  } finally {
    await unlink(listPath).catch(() => {})
  }
}
