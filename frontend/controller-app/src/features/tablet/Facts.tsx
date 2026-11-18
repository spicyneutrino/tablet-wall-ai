import { CircleCheck, CircleHelp, TriangleAlert } from 'lucide-react';
import { useEffect, useState } from 'react';
import { fleetPower, powerReadiness, POWER_HELP } from '../../domain/stagePanels';
import { useWallStore } from '../../state/hooks';
import { useShell } from '../preview/ShellContext';
import { useShellView } from '../preview/useShellView';
import { reportAge } from '../board/model';

function millimetres(value: number) {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

export default function Facts() {
  const { store } = useShell();
  const { tablets, server, config } = useShellView();
  const id = useWallStore(store, state => state.ui.drill ?? state.ui.selected);
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const tablet = tablets.find(tablet => tablet.id === id);
  if (!tablet) return null;
  const powerFor = (deviceId: string) => {
    const record = server.roster[deviceId];
    return powerReadiness(record ? { wake_lock: record.wake_lock ?? undefined, online: record.online,
      last_seen: record.last_seen ?? undefined } : null, { stale: !!server.rosterError, checkedAt: server.rosterCheckedAt });
  };
  const power = powerFor(tablet.id);
  const fleet = fleetPower(tablets.map(item => ({ online: server.roster[item.id]?.online === true, power: powerFor(item.id) })));
  const fleetNote = fleet && fleet.state !== 'held' ? `All online tablets report wake lock ${fleet.state}.` : null;
  const profile = config?.displays.filter(record => record.device_id === tablet.id).sort((a, b) => b.revision - a.revision)[0];
  const size = profile ? `${millimetres(profile.active_width_mm)} × ${millimetres(profile.active_height_mm)} mm`
    : tablet.model !== 'Model not set' ? 'From the model, not measured' : 'Not measured';
  const report = server.roster[tablet.id]?.online ? 'Now' : reportAge(tablet.lastSeen, now).label;
  const Icon = tablet.showing ? CircleCheck : tablet.tone === 'warn' || tablet.tone === 'err' ? TriangleAlert : CircleHelp;
  return <div className="tablet-facts-block">
    <dl className="tablet-facts">
      <dt className="t-muted">State</dt>
      <dd><span className={`state state-${tablet.tone}`}><Icon aria-hidden="true" /><span>{tablet.word}</span></span></dd>
      <dt className="t-muted">Last report</dt><dd>{report}</dd>
      <dt className="t-muted">Model</dt><dd>{tablet.model}</dd>
      <dt className="t-muted">Size</dt><dd>{size}</dd>
      <dt className="t-muted">Screen awake</dt><dd>{power.report}</dd>
    </dl>
    {fleetNote ? <div className="tablet-fleet-power">
      <p className="t-caption text-warn" data-fleet-power>{fleetNote}</p>
      <p className="t-caption t-muted" data-power-help>{POWER_HELP}</p>
    </div> : null}
  </div>;
}
