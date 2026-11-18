import { describe, it, expect } from 'vitest';
import cases from '../../../../tests/snapshot_names.json';
import { snapshotName } from './names';

describe('tests/snapshot_names.json', () => {
    it('matches the old snapshotName accept and reject results', () => {
        for (const item of cases) {
            expect(snapshotName(item.raw), item.raw).toBe(item.expect);
        }
    });
});
