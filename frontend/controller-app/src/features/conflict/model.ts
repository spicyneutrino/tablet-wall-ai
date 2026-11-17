import type { Layout } from '../../api/layouts';
import type { Scene, SceneInput } from '../../api/scene';
import type { WallStore } from '../../state/store';
import { formBaseline } from '../../state/drafts/tabletForms';
import type { FormKey, TabletForm } from '../../state/drafts/tabletForms';
import { layoutSignature } from '../../domain/layout';
import { boardView } from '../board/model';

export type ConflictItem =
  | { kind: 'arrangement' | 'content' | 'grid'; title: string; wall: string; mine: string; keepable: boolean }
  | { kind: 'form'; key: FormKey; title: string; wall: string; mine: string; keepable: true };

type Entry = Record<string, unknown>;
const plural = (count: number, one: string) => `${count} ${one}${count === 1 ? '' : 's'}`;
const hundredths = (value: unknown) => Math.round((typeof value === 'number' ? value : 0) * 100);
const entriesOf = (layout: Layout): Record<string, Entry> => layout.kind === 'logical' ? layout.placements : layout.slots;

function moved(kind: Layout['kind'], a: Entry, b: Entry) {
  if (kind === 'logical') return a.x !== b.x || a.y !== b.y;
  return (['center_x_mm', 'center_y_mm', 'nudge_x_mm', 'nudge_y_mm'] as const).some(key => hundredths(a[key]) !== hundredths(b[key]));
}

export function describeLayoutChange(from: Layout, to: Layout): string {
  if (from.kind !== to.kind) return `Switched to a ${to.kind} layout`;
  if (layoutSignature(from) === layoutSignature(to)) return 'Layout unchanged';
  const before = entriesOf(from), after = entriesOf(to);
  const shared = Object.keys(after).filter(id => before[id]);
  const count = (test: (a: Entry, b: Entry) => boolean) => shared.filter(id => test(before[id]!, after[id]!)).length;
  const counts: [number, string][] = [
    [count((a, b) => moved(to.kind, a, b)), 'moved'],
    [to.kind === 'physical' ? count((a, b) => a.mount_angle !== b.mount_angle) : 0, 'turned'],
    [to.kind === 'logical' ? count((a, b) => a.w !== b.w || a.h !== b.h) : 0, 'resized'],
    [Object.keys(after).filter(id => !before[id]).length, 'added'],
    [Object.keys(before).filter(id => !after[id]).length, 'removed'],
  ];
  const parts = counts.filter(([n]) => n).map(([n, word]) => word === 'moved' ? `${plural(n, 'tablet')} moved` : `${n} ${word}`);
  if (!parts.length && JSON.stringify(from.sizing) !== JSON.stringify(to.sizing)) parts.push('spacing changed');
  if (!parts.length && from.kind === 'logical' && to.kind === 'logical' && (from.width !== to.width || from.height !== to.height)) parts.push('wall size changed');
  const text = parts.join(', ') || 'layout changed';
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function describeScene(content: Scene | SceneInput | null | undefined): string {
  if (!content) return 'Nothing yet';
  if (content.type === 'image') {
    const name = 'name' in content && content.name ? content.name : 'Image';
    return `${name}, ${content.fit === 'contain' ? 'Fit' : 'Fill'}`;
  }
  return content.type === 'calibration' ? 'Calibration grid' : 'Tablet colours';
}

const fieldLabels: Record<string, string> = { name: 'Name', 'tablet-model': 'Model' };
function changedFields(a: Entry, b: Entry): string {
  const keys = [...new Set([...Object.keys(a), ...Object.keys(b)])]
    .filter(key => key !== '_revision' && JSON.stringify(a[key]) !== JSON.stringify(b[key]));
  return keys.length ? keys.map(key => fieldLabels[key] ?? key.replace(/_/g, ' ')).join(', ') : 'No fields changed';
}

const groupLabels = { name: 'name', model: 'model', profile: 'screen profile', calibration: 'calibration' } as const;

function formItem(state: WallStore, form: TabletForm, names: Record<string, string>): ConflictItem | null {
  const config = state.server.config;
  if (!config) return null;
  return { kind: 'form', key: `${form.id}:${form.group}`, title: `${names[form.id] ?? 'Tablet'} ${groupLabels[form.group]}`,
    wall: changedFields(form.baseline, formBaseline(config, form.id, form.group)),
    mine: changedFields(form.baseline, form.values), keepable: true };
}

export function conflictItems(state: WallStore): ConflictItem[] {
  const config = state.server.config;
  if (!config) return [];
  const { arrangement, content, grid } = state;
  const items: ConflictItem[] = [];
  if (arrangement?.conflict) items.push({ kind: 'arrangement', title: 'Layout',
    wall: describeLayoutChange(arrangement.base, config.layout),
    mine: describeLayoutChange(arrangement.base, arrangement.draft), keepable: true });
  if (content.conflict && content.selection) items.push({ kind: 'content', title: 'Image',
    wall: describeScene(config.scene.content), mine: describeScene(content.selection), keepable: !content.savedScene });
  if (grid?.stale) items.push({ kind: 'grid', title: 'Grid', wall: 'The wall or a tablet changed after your preview',
    mine: `${grid.command.columns} × ${grid.command.rows} grid, ${plural(grid.command.device_ids.length, 'tablet')}`, keepable: true });
  const forms = Object.values(state.forms).filter(form => form?.conflict);
  if (forms.length) {
    const names = Object.fromEntries(boardView(state.server, state.clock.nowMono).tablets.map(tablet => [tablet.id, tablet.name]));
    for (const form of forms) { const item = form && formItem(state, form, names); if (item) items.push(item); }
  }
  return items;
}
