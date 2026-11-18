import { LogIn } from 'lucide-react';
import { useShell } from '../preview/ShellContext';
import { useWallStore } from '../../state/hooks';

export default function SignedOut() {
  const { store } = useShell();
  const signedOut = useWallStore(store, state => state.server.transportText === 'Signed out');
  if (!signedOut) return null;
  return <a className="link inline-flex items-center gap-1" href="/auth/login?next=/controller/app/">
    <LogIn aria-hidden="true" className="size-4" />Sign in</a>;
}
