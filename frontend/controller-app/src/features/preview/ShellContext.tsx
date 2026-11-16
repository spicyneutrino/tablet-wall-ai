import { createContext, useContext } from 'react';
import type { Session } from '../../session/session';
import type { WallStoreApi } from '../../state/store';

export const ShellContext = createContext<{ store: WallStoreApi; session: Session } | null>(null);

export function useShell() {
  const shell = useContext(ShellContext);
  if (!shell) throw new Error('Shell features must be inside App.');
  return shell;
}
