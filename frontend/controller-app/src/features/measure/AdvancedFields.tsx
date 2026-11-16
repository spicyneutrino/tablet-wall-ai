import { ChevronRight } from 'lucide-react';
import MeasureField from './MeasureField';
import type { Values } from './model';

export default function AdvancedFields({ values, errors, change }: {
  values: Values; errors: Values; change: (key: string, value: string) => void;
}) {
  const field = (name: string, label: string, unit = '', options?: readonly string[], text?: boolean) =>
    <MeasureField key={name} name={name} label={label} value={values[name] ?? ''} onChange={change}
      error={errors[name]} unit={unit} options={options} text={text} />;
  return <details className="measure-advanced"><summary><ChevronRight className="chev" aria-hidden="true" />Advanced: quarter turn, anchor, offsets</summary>
    <p className="t-caption">Quarter turn maps browser axes to the native panel. Changing these values invalidates the ruler check. Verify browser insets and offsets before saving. Choosing ruler values uses the checked live viewport and derived scales on save.</p>
    <div className="measure-grid">
      {field('calQuarterTurn', 'Quarter turn', '', ['0', '1', '2', '3'])}
      {field('calAnchorEdge', 'Anchor', '', ['top-left', 'top-right', 'bottom-left', 'bottom-right'])}
      {field('calOffsetX', 'Panel offset X', 'mm')}{field('calOffsetY', 'Panel offset Y', 'mm')}
      {field('calViewportWidth', 'Viewport width', 'px')}{field('calViewportHeight', 'Viewport height', 'px')}
      {field('calDpr', 'Device pixel ratio')}{field('calOrientation', 'Orientation', '', ['', '0', '90', '180', '270'])}
      {field('calMode', 'Browser mode', '', ['', 'tab', 'fullscreen', 'standalone'])}
      {field('calUncertainty', 'Uncertainty', 'mm')}
      {field('calMmCssX', 'Scale X', 'mm/px')}{field('calMmCssY', 'Scale Y', 'mm/px')}
      {field('calMethod', 'Method', '', undefined, true)}{field('profileLabel', 'Profile label', '', undefined, true)}
      {field('profileProvenance', 'Provenance', '', undefined, true)}
      {field('profilePixelWidth', 'Panel pixel width', 'px')}{field('profilePixelHeight', 'Panel pixel height', 'px')}
    </div>
  </details>;
}
