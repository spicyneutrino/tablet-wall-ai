import { expect, it, vi } from 'vitest';
import upload from '../../api/__fixtures__/upload.json';
import { UPLOAD_FAILED, UPLOAD_REFUSED, UPLOAD_TIMEOUT_MS, formatBytes, uploadFile } from './upload';
import type { UploadXhr } from './upload';

function fakeXhr() {
  const xhr: UploadXhr & { opened: [string, string] | null; headers: Record<string, string>;
    body: unknown; aborted: boolean; finish: (status: number, body: string) => void } = {
    timeout: 0, status: 0, responseText: '', opened: null, headers: {}, body: null, aborted: false,
    upload: { onprogress: null, onload: null },
    onload: null, onerror: null, ontimeout: null, onabort: null,
    open(method, url) { this.opened = [method, url]; },
    setRequestHeader(name, value) { this.headers[name] = value; },
    send(body) { this.body = body; },
    abort() { this.aborted = true; this.onabort?.(); },
    finish(status, body) { this.status = status; this.responseText = body; this.onload?.(); },
  };
  return xhr;
}

function file(name: string, type = 'image/png') {
  return { name, type, size: 2048 };
}

it('posts one raw body to the encoded upload path and reports progress', async () => {
  const xhr = fakeXhr(), progress: number[] = [], transfer = vi.fn(), source = file('open house.png');
  const handle = uploadFile(source, {
    createXhr: () => xhr, onProgress: percent => progress.push(percent), onTransferComplete: transfer,
  });
  expect(xhr.opened).toEqual(['POST', '/uploads?name=open%20house.png']);
  expect(xhr.headers).toEqual({ 'Content-Type': 'image/png' });
  expect(xhr.timeout).toBe(UPLOAD_TIMEOUT_MS);
  expect(xhr.body).toBe(source);
  xhr.upload.onprogress?.({ lengthComputable: true, loaded: 512, total: 2048 });
  xhr.upload.onprogress?.({ lengthComputable: true, loaded: 4096, total: 2048 });
  xhr.upload.onprogress?.({ lengthComputable: false, loaded: 1, total: 0 });
  expect(progress).toEqual([25, 100]);
  xhr.upload.onload?.();
  expect(transfer).toHaveBeenCalledTimes(1);
  xhr.finish(201, JSON.stringify(upload));
  await expect(handle.done).resolves.toEqual({ kind: 'ready', asset: upload.asset });
});

it('uses an octet-stream content type when the file names none', async () => {
  const xhr = fakeXhr();
  uploadFile(file('scan', ''), { createXhr: () => xhr });
  expect(xhr.headers['Content-Type']).toBe('application/octet-stream');
});

it('reports a 415 as a refusal without showing the server body', async () => {
  const xhr = fakeXhr();
  const handle = uploadFile(file('banner.heic', 'image/heic'), { createXhr: () => xhr });
  xhr.finish(415, JSON.stringify({ detail: 'only image/jpeg, image/png is accepted' }));
  await expect(handle.done).resolves.toEqual({ kind: 'refused' });
  expect(UPLOAD_REFUSED).toBe('This file type is not accepted');
});

it('reports a 500, a network error and a timeout as a retryable failure', async () => {
  const server = fakeXhr();
  const serverHandle = uploadFile(file('a.png'), { createXhr: () => server });
  server.finish(500, JSON.stringify({ detail: 'upload failed (OSError)' }));
  await expect(serverHandle.done).resolves.toEqual({ kind: 'failed' });
  expect(UPLOAD_FAILED).toBe('Upload failed. Try again.');

  const network = fakeXhr();
  const networkHandle = uploadFile(file('b.png'), { createXhr: () => network });
  network.onerror?.();
  await expect(networkHandle.done).resolves.toEqual({ kind: 'failed' });

  const timeout = fakeXhr();
  const timeoutHandle = uploadFile(file('c.png'), { createXhr: () => timeout });
  timeout.ontimeout?.();
  await expect(timeoutHandle.done).resolves.toEqual({ kind: 'failed' });
});

it('reports malformed and incomplete success bodies as a failure', async () => {
  for (const body of ['{unreadable', '{}', JSON.stringify({ state: 'ready', asset: { name: 'x' } })]) {
    const xhr = fakeXhr();
    const handle = uploadFile(file('a.png'), { createXhr: () => xhr });
    xhr.finish(201, body);
    await expect(handle.done).resolves.toEqual({ kind: 'failed' });
  }
});

it('cancels the transfer by aborting the request', async () => {
  const xhr = fakeXhr();
  const handle = uploadFile(file('a.png'), { createXhr: () => xhr });
  handle.cancel();
  expect(xhr.aborted).toBe(true);
  await expect(handle.done).resolves.toEqual({ kind: 'cancelled' });
});

it('formats byte sizes for the queue', () => {
  expect(formatBytes(900)).toBe('900 B');
  expect(formatBytes(2048)).toBe('2.0 KB');
  expect(formatBytes(2.5 * 1024 * 1024)).toBe('2.5 MB');
});
