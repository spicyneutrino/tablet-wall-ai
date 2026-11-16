import { createElement, useState } from 'react';
import { useWallStore } from '../../state/hooks';
import { patternOutcomeText, showTestPattern } from '../../state/commands/testPatterns';
import { useShell } from './ShellContext';
import type { PreviewAction } from './PrimaryAction';

export function useContentAction(): PreviewAction | null {
  const { store, session } = useShell();
  const pattern = useWallStore(store, state => state.ui.testPattern);
  const [message, setMessage] = useState('');
  if (!pattern) return null;
  return {
    label: 'Show on wall',
    busyLabel: 'Showing…',
    onClick: () => { void showTestPattern(store, session, pattern).then(outcome => setMessage(patternOutcomeText(outcome))); },
    secondary: message ? createElement('p', { className: 't-caption', role: 'status' }, message) : undefined,
  };
}
