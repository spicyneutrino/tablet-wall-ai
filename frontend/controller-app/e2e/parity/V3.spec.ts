import { mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { expect, test } from '../fixtures';

test('V3 Backup facts show the last manifest and restore rehearsal, or "not recorded"', async ({ page, server, guard }) => {
  await guard(page);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('status')).toHaveText('Live operator updates connected.');
  await page.getByRole('button', { name: 'Server', exact: true }).click();
  const sheet = page.getByRole('dialog', { name: 'Server', exact: true });
  await sheet.getByRole('tab', { name: 'Backup and reset', exact: true }).click();
  const manifest = sheet.locator('dt', { hasText: 'Last manifest' }).locator('xpath=following-sibling::dd[1]');
  const rehearsal = sheet.locator('dt', { hasText: 'Restore rehearsal' }).locator('xpath=following-sibling::dd[1]');
  await expect(manifest).toHaveText('not recorded');
  await expect(rehearsal).toHaveText('not recorded');
  await expect(sheet.getByRole('button', { name: /backup/i })).toHaveCount(0);

  const backupDir = join(server.directory, 'backups');
  await mkdir(backupDir, { recursive: true });
  const manifestAt = '2026-11-15T16:00:00Z';
  const rehearsalAt = '2026-11-15T16:30:00Z';
  await writeFile(join(backupDir, 'manifest.json'), JSON.stringify({ created_utc: manifestAt }));
  await writeFile(join(backupDir, 'restore-rehearsal.json'), JSON.stringify({ completed_utc: rehearsalAt }));
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Server', exact: true }).click();
  await sheet.getByRole('tab', { name: 'Backup and reset', exact: true }).click();
  await expect(manifest).toHaveText(manifestAt);
  await expect(rehearsal).toHaveText(rehearsalAt);
  await expect(sheet.getByRole('button', { name: /backup/i })).toHaveCount(0);
});
