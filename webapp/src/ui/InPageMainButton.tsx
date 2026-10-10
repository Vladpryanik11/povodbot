import { useMainButtonState, useTg } from '../telegram/hooks';
import { Button } from './Button';
import styles from './InPageMainButton.module.css';

/** Draws the Telegram main button inside the page when the client cannot (browser, old clients). */
export function InPageMainButton() {
  const tg = useTg();
  const state = useMainButtonState();
  if (tg.hasNativeMainButton || !state) return null;
  return (
    <div className={styles.dock}>
      <Button wide disabled={!state.enabled} loading={state.progress} onClick={() => state.onClick()}>
        {state.text}
      </Button>
    </div>
  );
}
