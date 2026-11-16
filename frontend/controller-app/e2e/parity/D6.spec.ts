import { test } from '../fixtures';

test.use({ serverScope: 'parity-D6' });
test.fixme('D6 A late or out-of-order read never overwrites newer state', async () => {});
