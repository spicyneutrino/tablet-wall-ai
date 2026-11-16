import { test } from '../fixtures';

test.use({ serverScope: 'parity-P1' });
test.fixme('P1 Opt-in shows the playlist controls. Editing and saving the playlist sends `If-Match` with the playlist ETag. A stale ETag gives 412 and keeps the edits', async () => {});
