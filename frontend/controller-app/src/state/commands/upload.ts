import { UploadResponseSchema } from '../../api/images';
import type { ManagedAsset } from '../../api/images';
import { paths } from '../../api/paths';

export const UPLOAD_TIMEOUT_MS = 120_000;
export const UPLOAD_REFUSED = 'This file type is not accepted';
export const UPLOAD_FAILED = 'Upload failed. Try again.';
export const UPLOADS_OFF = 'Uploads are off on this server';

export type UploadResult =
  | { kind: 'ready'; asset: ManagedAsset }
  | { kind: 'refused' }
  | { kind: 'failed' }
  | { kind: 'cancelled' };

export type UploadFile = Pick<File, 'name' | 'type' | 'size'>;
export type ProgressEventLike = { lengthComputable: boolean; loaded: number; total: number };
export type UploadXhr = {
  timeout: number; status: number; responseText: string;
  upload: { onprogress: ((event: ProgressEventLike) => void) | null; onload: (() => void) | null };
  onload: (() => void) | null; onerror: (() => void) | null;
  ontimeout: (() => void) | null; onabort: (() => void) | null;
  open(method: string, url: string): void;
  setRequestHeader(name: string, value: string): void;
  send(body: unknown): void;
  abort(): void;
};
export type UploadHandle = { done: Promise<UploadResult>; cancel: () => void };

function createBrowserXhr(): UploadXhr {
  return new XMLHttpRequest() as unknown as UploadXhr;
}

export function uploadFile(file: UploadFile, options: {
  onProgress?: (percent: number) => void;
  onTransferComplete?: () => void;
  createXhr?: () => UploadXhr;
} = {}): UploadHandle {
  const xhr: UploadXhr = (options.createXhr ?? createBrowserXhr)();
  let settle: (result: UploadResult) => void = () => {};
  let settled = false;
  const done = new Promise<UploadResult>((resolve) => { settle = resolve; });
  function finish(result: UploadResult) {
    if (settled) return;
    settled = true;
    settle(result);
  }
  xhr.timeout = UPLOAD_TIMEOUT_MS;
  xhr.open('POST', paths.upload(file.name));
  xhr.setRequestHeader('Content-Type', file.type || 'application/octet-stream');
  xhr.upload.onprogress = (event) => {
    if (!event.lengthComputable || event.total <= 0) return;
    options.onProgress?.(Math.min(100, Math.max(0, event.loaded / event.total * 100)));
  };
  xhr.upload.onload = () => { options.onTransferComplete?.(); };
  xhr.onload = () => {
    let payload: unknown = null;
    try { payload = JSON.parse(xhr.responseText); } catch { payload = null; }
    const parsed = UploadResponseSchema.safeParse(payload);
    if (xhr.status >= 200 && xhr.status < 300 && parsed.success) finish({ kind: 'ready', asset: parsed.data.asset });
    else if (xhr.status === 415) finish({ kind: 'refused' });
    else finish({ kind: 'failed' });
  };
  xhr.onerror = () => finish({ kind: 'failed' });
  xhr.ontimeout = () => finish({ kind: 'failed' });
  xhr.onabort = () => finish({ kind: 'cancelled' });
  xhr.send(file);
  return { done, cancel: () => xhr.abort() };
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
