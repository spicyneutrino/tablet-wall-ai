import { useState } from 'react';
import { Button } from '../../ui/Button';
import { ModalDialog } from '../../ui/ModalDialog';

const RESTORE_COMMAND = `uv run python deploy/backup.py restore \\
  --src /path/to/snapshot \\
  --db /path/to/restored/wall.db \\
  --assets /path/to/restored/assets \\
  --media /path/to/restored/media`;

export default function HowToRestore() {
  const [open, setOpen] = useState(false);
  return <>
    <Button variant="ghost" onClick={() => setOpen(true)}>How to restore</Button>
    {/* The Server panel is itself a dialog: stop its close handler from firing when this one closes. */}
    <ModalDialog open={open} onOpenChange={setOpen} title="How to restore" onClose={event => event.stopPropagation()}>
      <div className="restore-help">
        <p className="t-body">This console cannot restore a backup. Restoring runs on the wall’s computer, from the server command line.</p>
        <ol className="restore-steps t-body">
          <li>Stop the Tablet Wall server. Restore cannot tell whether it is running.</li>
          <li>Choose new folders for the database, the images and the media. Restore never overwrites, so the files you have now stay untouched. It checks the snapshot first and stops if the check fails. A snapshot that holds managed media needs the media folder too. Run this in the project folder, with your own paths:
            <pre className="restore-command t-caption">{RESTORE_COMMAND}</pre>
          </li>
          <li>Point <code>TABLET_WALL_DB</code>, <code>TABLET_WALL_ASSET_DIR</code> and <code>TABLET_WALL_MEDIA_DIR</code> at the new paths, then start the server.</li>
          <li>Check the wall: the layout, the images, and the tablets reconnecting. Restored tablets start offline until they reconnect.</li>
          <li>Keep the old folders until the restored copy has been used. To go back, point the three settings at them again and restart.</li>
        </ol>
        <p className="t-caption">Full steps: Restore drill in deploy/OPERATIONS.md.</p>
      </div>
    </ModalDialog>
  </>;
}
