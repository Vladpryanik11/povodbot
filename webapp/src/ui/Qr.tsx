import QRCode from 'qrcode';
import { useEffect, useState } from 'react';
import styles from './Qr.module.css';

/** Always black on a white plate with a quiet zone, in both themes, so door scanners read it. */
export function Qr({ value, size = 260 }: { value: string; size?: number }) {
  const [svg, setSvg] = useState('');
  useEffect(() => {
    let alive = true;
    QRCode.toString(value, { type: 'svg', margin: 2, errorCorrectionLevel: 'M', color: { dark: '#000000', light: '#ffffff' } })
      .then((markup) => alive && setSvg(markup))
      .catch(() => alive && setSvg(''));
    return () => {
      alive = false;
    };
  }, [value]);
  return (
    <div
      className={styles.plate}
      role="img"
      aria-label="QR-код билета"
      style={{ width: size, height: size }}
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
