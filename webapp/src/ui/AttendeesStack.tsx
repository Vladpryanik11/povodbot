import { plural } from '../lib/format';
import styles from './AttendeesStack.module.css';

/** Up to three faces of guests who agreed to be shown, then «+N» for everyone else. */
export function AttendeesStack({ count, avatars }: { count: number; avatars: string[] }) {
  if (count <= 0) return null;
  const faces = avatars.slice(0, 3);
  const rest = count - faces.length;
  return (
    <span className={styles.stack} role="img" aria-label={`Идут ${count} ${plural(count, ['человек', 'человека', 'человек'])}`}>
      {faces.map((url) => (
        <img key={url} className={styles.face} src={url} alt="" />
      ))}
      {rest > 0 ? <span className={styles.more}>+{rest}</span> : null}
    </span>
  );
}
