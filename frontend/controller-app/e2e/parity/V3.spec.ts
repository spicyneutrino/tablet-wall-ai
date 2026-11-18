import { mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { expect, test } from '../fixtures';

test.use({ serverScope: 'parity-V3' });

test('V3 Backup facts show the last manifest and restore rehearsal, or "not recorded"', async ({ page, server, guard }) => {
  await guard(page);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('status')).toHaveText('Live operator updates connected.');
  await page.getByRole('button', { name: 'Server', exact: true }).click();
  const sheet = page.getByRole('dialog', { name: 'Server', exact: true });
  await sheet.getByRole('tab', { name: 'Backup and reset', exact: true }).click();
  const manifest = sheet.locator('dt', { hasText: 'Last snapshot' }).locator('xpath=following-sibling::dd[1]');
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

test('V3 How to restore opens in-app steps from the deploy runbook and writes nothing', async ({ page, server, guard, writes }) => {
  await guard(page);
  await page.goto(`${server.origin}/controller/app/`, { waitUntil: 'domcontentloaded' });
  await expect(page.getByRole('status')).toHaveText('Live operator updates connected.');
  const recorded = writes(page);
  await page.getByRole('button', { name: 'Server', exact: true }).click();
  const sheet = page.getByRole('dialog', { name: 'Server', exact: true });
  await sheet.getByRole('tab', { name: 'Backup and reset', exact: true }).click();
  await sheet.getByRole('button', { name: 'How to restore', exact: true }).click();
  const help = page.getByRole('dialog', { name: 'How to restore', exact: true });
  await expect(help).toBeVisible();
  await expect(help.getByRole('listitem')).toHaveCount(5);
  await expect(help).toContainText('deploy/backup.py restore');
  await expect(help).toContainText('TABLET_WALL_DB');
  await expect(help).toContainText('deploy/OPERATIONS.md');
  await page.keyboard.press('Escape');
  await expect(help).toBeHidden();
  await expect(sheet).toBeVisible();
  await expect(sheet.getByRole('button', { name: 'How to restore', exact: true })).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(sheet).toHaveCount(0);
  expect(recorded).toHaveLength(0);
});
