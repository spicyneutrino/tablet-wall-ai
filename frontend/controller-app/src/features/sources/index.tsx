import { Tabs, TabsList, TabsTrigger, TabsContent } from '../../ui/Tabs';
import { useWallStore } from '../../state/hooks';
import { useShell } from '../preview/ShellContext';
import PrimaryAction from '../preview/PrimaryAction';
import Images from './images';
import Saved from './saved';
import Layouts from './layouts';
import Tests from './tests';

const sources = [
  { value: 'images', label: 'Images', Component: Images },
  { value: 'saved', label: 'Saved', Component: Saved },
  { value: 'layouts', label: 'Layouts', Component: Layouts },
  { value: 'tests', label: 'Tests', Component: Tests },
] as const;

export default function Sources() {
  const { store } = useShell();
  const source = useWallStore(store, state => state.ui.source);
  return <section className="sources-section" aria-label="Sources">
    <Tabs className="source-tabs" value={source} onValueChange={value => {
      const entry = sources.find(entry => entry.value === value);
      if (entry) store.setState(state => ({ ui: { ...state.ui, source: entry.value } }));
    }}>
      <TabsList aria-label="Source type">{sources.map(entry => <TabsTrigger key={entry.value} value={entry.value}>{entry.label}</TabsTrigger>)}</TabsList>
      {sources.map(({ value, Component }) => <TabsContent key={value} value={value}><Component /></TabsContent>)}
    </Tabs>
    <PrimaryAction />
  </section>;
}
