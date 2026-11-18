const tablets = [
  { x: 0, y: 0, width: 242.1, height: 179 },
  { x: 263.1, y: 4.75, width: 240, height: 169.5 },
  { x: 0, y: 199, width: 203.2, height: 134.8 },
  { x: 263.1, y: 199.05, width: 200, height: 134.7 },
];

export default function WallPlaceholder({ loading = false }: { loading?: boolean }) {
  return <svg viewBox="-32 -63.817 567.1 461.434" aria-hidden="true">
    <rect x="-6" y="-6" width="515.1" height="345.8" rx="6" fill="none"
      stroke="var(--stage-line)" strokeDasharray="6 6" vectorEffect="non-scaling-stroke" />
    {loading ? tablets.map((tablet, index) => <rect key={index} {...tablet} rx="10"
      fill="var(--stage-body)" className="skel-pulse" />) : null}
  </svg>;
}
