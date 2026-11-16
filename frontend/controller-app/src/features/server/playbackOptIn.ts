/** U30 reads this key. Absent or any value other than `on` means playback stays hidden. */
export const PLAYBACK_OPT_IN_KEY = 'tablet-wall-playback';

export function readPlaybackOptIn(): boolean {
  try { return localStorage.getItem(PLAYBACK_OPT_IN_KEY) === 'on'; } catch { return false; }
}

export function writePlaybackOptIn(on: boolean): boolean {
  try {
    localStorage.setItem(PLAYBACK_OPT_IN_KEY, on ? 'on' : 'off');
    return true;
  } catch { return false; }
}
