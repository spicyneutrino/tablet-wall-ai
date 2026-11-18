import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const run = promisify(execFile);

// The server ingests only H.264 in MP4/MOV (tabletwall/video.py), so a VP8/VP9 WebM
// cannot be uploaded. This is the same ffmpeg recipe as simulator/browser/video_run.py:
// Constrained Baseline, yuv420p, faststart, no audio. testsrc2 moves, so playback is visible.
export async function makeClip(target: string, seconds = 3) {
  await run('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y',
    '-f', 'lavfi', '-i', `testsrc2=size=320x180:rate=10:duration=${seconds}`,
    '-c:v', 'libx264', '-profile:v', 'baseline', '-level', '3.0',
    '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-an', target]);
  return target;
}
