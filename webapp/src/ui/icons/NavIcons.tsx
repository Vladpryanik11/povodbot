/* Owner's tab icons (home.svg, heart.svg, profile.svg beside this file), paths verbatim. */

type Props = { filled: boolean };

function paint(filled: boolean) {
  return filled
    ? { fill: 'currentColor', stroke: 'none' }
    : { fill: 'none', stroke: 'currentColor', strokeWidth: 1.7, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const };
}

export function HomeIcon({ filled }: Props) {
  return (
    <svg width={26} height={26} viewBox="0 0 24 24" aria-hidden="true" {...paint(filled)}>
      <path
        fillRule="evenodd"
        d="M12 2.35c-.38 0-.75.14-1.04.4l-8.1 7.15c-.34.3-.54.74-.54 1.2v8.24c0 1.02.83 1.85 1.85 1.85h5.25v-6.52c0-.49.4-.89.9-.89h3.36c.5 0 .9.4.9.89v6.52h5.25c1.02 0 1.85-.83 1.85-1.85V11.1c0-.46-.2-.9-.54-1.2l-8.1-7.15c-.29-.26-.66-.4-1.04-.4Z"
      />
    </svg>
  );
}

export function HeartIcon({ filled }: Props) {
  return (
    <svg width={26} height={26} viewBox="0 0 24 24" aria-hidden="true" {...paint(filled)}>
      <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78Z" />
    </svg>
  );
}

export function ProfileIcon({ filled }: Props) {
  return (
    <svg width={26} height={26} viewBox="0 0 24 24" aria-hidden="true" {...paint(filled)}>
      <circle cx="12" cy="6.8" r="3.7" />
      <path d="M4.1 20.9v-1.15a7.9 7.9 0 0 1 15.8 0v1.15H4.1Z" />
    </svg>
  );
}
