import { test } from '../fixtures';

test.use({ serverScope: 'parity-M2' });
test.fixme('M2 The ruler check writes nothing. Its review is invalidated when the viewport or inputs change, and a stale review cannot be saved', async () => {});
