import { useMainButtonState } from '../telegram/hooks';
import { Button } from './Button';
import styles from './BottomBar.module.css';

/** Glass bar at the bottom of the page: summary on the left, the white main button on the right (spec v2 §5). */
export function BottomBar() {
  const state = useMainButtonState();
  if (!state) return null;
  return (
    <div className={`glass ${styles.bar}`}>
      {state.summary ? <span className={`t-price ${styles.summary}`}>{state.summary}</span> : null}
      <Button
        className={styles.button}
        wide={!state.summary}
        disabled={!state.enabled}
        loading={state.progress}
        // While in progress the button stays white with a spinner but takes no second tap, as Telegram's did.
        onClick={() => {
          if (!state.progress) state.onClick();
        }}
      >
        {state.text}
      </Button>
    </div>
  );
}
