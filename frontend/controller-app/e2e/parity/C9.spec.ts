import { test } from '../fixtures';

test.use({ serverScope: 'parity-C9' });
test.fixme('C9 A timeout, 5xx or unreadable response on Show gives "Not confirmed". Further writes are refused until Refresh status', async () => {});
