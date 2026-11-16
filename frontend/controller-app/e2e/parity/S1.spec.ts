import { test } from '../fixtures';

test.use({ serverScope: 'parity-S1' });
test.fixme('S1 Board status matches `tabletState` for displayed, stale (evidence older than 15 s), offline, excluded, identifying, unplaced, wrong content and missing tablet', async () => {});
