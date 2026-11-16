import type { ContentDraft } from '../../../state/drafts/content';
import { Button } from '../../../ui/Button';
import { FitControls } from './FitControls';

export function ContentActionFeedback({ content, message, fitOpen, setFitOpen, discard, rebuild }: {
  content: ContentDraft; message: string; fitOpen: boolean; setFitOpen: (open: boolean) => void;
  discard: () => void; rebuild: () => void;
}) {
  return <>
    {content.selection ? <div className="image-action-options">
      {content.conflict ? <Button variant="secondary" data-rebuild-preview onClick={rebuild}>Rebuild preview</Button>
        : content.selection.type === 'image' ? <Button variant="ghost" size="sm" onClick={() => setFitOpen(true)}>
          {content.selection.fit === 'contain' ? 'Fit' : 'Fill'} · Fit and crop</Button> : null}
      <Button variant="ghost" size="sm" onClick={discard}>Discard</Button>
    </div> : null}
    <p className="t-caption" role="status">{message}</p>
    {content.selection?.type === 'image' ? <FitControls open={fitOpen} onOpenChange={setFitOpen} /> : null}
  </>;
}
