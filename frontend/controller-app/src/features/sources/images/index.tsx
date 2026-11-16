import { Upload } from 'lucide-react';
import { useShellView } from '../../preview/useShellView';

export default function Images() {
  const { config, loading } = useShellView();
  const image = config?.scene.content;
  return <div className="source-strip" role="group" tabIndex={0} aria-label={loading ? 'Loading sources' : 'Source previews'}>
    {loading ? [0, 1, 2].map(index => <div className="source-preview" aria-hidden="true" key={index}>
      <span className="thumb skel" /><span className={`skel h-3 ${['w-20', 'w-16', 'w-12'][index]}`} /></div>) : <>
      {image?.type === 'image' && image.url && image.available !== false ? <figure className="source-preview"><span className="thumb">
        <img src={image.url} alt="" width="120" height="76" /></span><figcaption className="t-caption">{image.name || 'Wall image'}</figcaption></figure> : null}
      <figure className="source-preview"><span className="thumb dark"><svg viewBox="0 0 120 76" width="120" height="76" aria-hidden="true">
        <path d="M0 19H120M0 38H120M0 57H120M20 0V76M40 0V76M60 0V76M80 0V76M100 0V76" fill="none" stroke="currentColor" />
      </svg></span><figcaption className="t-caption">Calibration grid</figcaption></figure>
      <figure className="source-preview"><span className="thumb dark" /><figcaption className="t-caption">Black</figcaption></figure>
      <figure className="source-preview"><span className="thumb"><Upload aria-hidden="true" /></span><figcaption className="t-caption">Upload…</figcaption></figure>
    </>}
  </div>;
}
