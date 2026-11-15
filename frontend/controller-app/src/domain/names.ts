// Ported from frontend/controller/operator-forms.js (`snapshotName`).
const SNAPSHOT_NAME = /^[A-Za-z0-9][A-Za-z0-9 ._-]{0,63}$/;

export function snapshotName(raw: unknown): string | null {
    const name = raw == null ? "" : String(raw).trim();
    return SNAPSHOT_NAME.test(name) ? name : null;
}
