import { test } from '../fixtures';

test.use({ serverScope: 'parity-X13' });
test.fixme('X13 Long Unicode tablet and image names stay readable at every width. A missing thumbnail shows a fallback', async () => {});
