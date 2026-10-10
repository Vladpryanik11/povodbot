import styles from './Toggle.module.css';

interface Props {
  checked: boolean;
  label: string;
  disabled?: boolean;
  onChange(next: boolean): void;
}

/** On/off switch; white when on, like the primary button. */
export function Toggle({ checked, label, disabled = false, onChange }: Props) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      className={styles.toggle}
      onClick={() => onChange(!checked)}
    >
      <span className={styles.knob} aria-hidden="true" />
    </button>
  );
}
