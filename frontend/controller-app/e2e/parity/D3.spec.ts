import { test } from '../fixtures';

test.use({ serverScope: 'parity-D3' });
test.fixme('D3 A second controller\'s write marks the ETag stale. With a dirty draft, the conflict banner appears. Use theirs discards. Keep mine re-guards, and the next Apply succeeds', async () => {});
