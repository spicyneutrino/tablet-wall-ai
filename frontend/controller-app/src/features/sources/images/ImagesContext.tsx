import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { ImagesSchema } from '../../../api/images';
import type { Image } from '../../../api/images';
import { useWallStore } from '../../../state/hooks';
import { useShell } from '../../preview/ShellContext';

type Inventory = { images: Image[]; loading: boolean; error: string | null };
const ImagesContext = createContext<(Inventory & { refresh: () => void }) | null>(null);

export function ImagesProvider({ children }: { children: ReactNode }) {
  const { session, store } = useShell();
  const appliedAsset = useWallStore(store, state => state.server.config?.scene.content.type === 'image'
    ? state.server.config.scene.content.asset : null);
  const [version, setVersion] = useState(0);
  const [inventory, setInventory] = useState<Inventory>({ images: [], loading: true, error: null });
  useEffect(() => {
    let current = true;
    void session.request('GET', '/api/v3/images', undefined, { parse: ImagesSchema }).then(outcome => {
      if (!current) return;
      if (outcome.kind === 'ok') setInventory({ images: outcome.value.images, loading: false, error: null });
      else setInventory(previous => ({ ...previous, loading: false,
        error: 'Image library unavailable. Refresh images to retry.' }));
    });
    return () => { current = false; };
  }, [session, version, appliedAsset]);
  return <ImagesContext value={{ ...inventory, refresh: () => {
    setInventory(previous => ({ ...previous, loading: true, error: null }));
    setVersion(previous => previous + 1);
  } }}>{children}</ImagesContext>;
}

export function useImages() {
  const inventory = useContext(ImagesContext);
  if (!inventory) throw new Error('Image sources must be inside ImagesProvider.');
  return inventory;
}
