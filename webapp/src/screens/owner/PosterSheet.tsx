import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react';
import { MSG } from '../../api/owner/messages';
import { OwnerApiError } from '../../api/owner/OwnerApi';
import { useOwnerApi } from '../../api/owner/OwnerApiProvider';
import type { Focus, OwnerEvent } from '../../api/owner/types';
import type { Poster } from '../../api/types';
import { Button } from '../../ui/Button';
import styles from './PosterSheet.module.css';

const MAX_PHOTO_BYTES = 15 * 1024 * 1024;
const ACCEPT = 'image/jpeg,image/png,image/webp,image/heic,image/heif';
const CENTER: Focus = { x: 0.5, y: 0.5 };
const KEY_STEP = 0.05;

/** Where the poster is cut on the guest's screens. */
const CROPS = [
  { name: 'Скоро', ratio: '4 / 5' },
  { name: 'На этой неделе', ratio: '16 / 9' },
  { name: 'Билет', ratio: '3 / 1' },
];

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const round3 = (v: number) => Math.round(v * 1000) / 1000;

/** A tap inside `rect` as a 0–1 point, edges clamped; null for a box with no size. */
export function focusFromTap(
  clientX: number,
  clientY: number,
  rect: { left: number; top: number; width: number; height: number },
): Focus | null {
  if (!(rect.width > 0) || !(rect.height > 0)) return null;
  return {
    x: round3(clamp01((clientX - rect.left) / rect.width)),
    y: round3(clamp01((clientY - rect.top) / rect.height)),
  };
}

/** Same rounding as ui/PosterImage. */
export function objectPosition(focus: Focus): string {
  return `${Math.round(focus.x * 100)}% ${Math.round(focus.y * 100)}%`;
}

const ARROWS: Record<string, Focus> = {
  ArrowLeft: { x: -KEY_STEP, y: 0 },
  ArrowRight: { x: KEY_STEP, y: 0 },
  ArrowUp: { x: 0, y: -KEY_STEP },
  ArrowDown: { x: 0, y: KEY_STEP },
};

interface Props {
  eventId: string;
  poster: Poster | null;
  onDone(event: OwnerEvent): void;
  onClose(): void;
}

/** Pick a photo, tap its main point, check the three crops, upload (spec §3.3). */
export function PosterSheet({ eventId, poster, onDone, onClose }: Props) {
  const api = useOwnerApi();
  const titleId = useId();
  const fileInput = useRef<HTMLInputElement>(null);
  const initial: Focus = poster ? { x: poster.focusX, y: poster.focusY } : CENTER;
  const [file, setFile] = useState<File | null>(null);
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  const [focus, setFocus] = useState<Focus>(initial);
  const [broken, setBroken] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);

  // The picked photo's object URL lives until another photo is picked or the sheet closes.
  useEffect(() => () => {
    if (fileUrl) URL.revokeObjectURL(fileUrl);
  }, [fileUrl]);

  const url = fileUrl ?? poster?.url ?? null;

  function choose(picked: File | undefined) {
    if (!picked) return;
    if (picked.size > MAX_PHOTO_BYTES) {
      setError(MSG.photoTooBig);
      return;
    }
    setFile(picked);
    setFileUrl(URL.createObjectURL(picked));
    setFocus(CENTER);
    setBroken(false);
    setError(null);
  }

  function nudge(event: KeyboardEvent) {
    const step = ARROWS[event.key];
    if (!step) return;
    event.preventDefault();
    setFocus((f) => ({ x: round3(clamp01(f.x + step.x)), y: round3(clamp01(f.y + step.y)) }));
  }

  async function done() {
    if (inFlight.current) return;
    const moved = !broken && (focus.x !== initial.x || focus.y !== initial.y);
    const run = file
      ? () => api.uploadPoster(eventId, file, broken ? CENTER : focus)
      : moved
        ? () => api.setPosterFocus(eventId, focus)
        : null;
    if (!run) {
      onClose();
      return;
    }
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      onDone(await run());
    } catch (e) {
      const known = e instanceof OwnerApiError ? e : null;
      setError(known === null ? MSG.unknown : known.status === 0 ? MSG.network : known.message);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <div className={styles.overlay}>
      <div
        className={styles.sheet}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onKeyDown={(e) => e.key === 'Escape' && onClose()}
      >
        <h2 id={titleId} className={`t-h2 ${styles.title}`}>
          Постер
        </h2>
        <input
          ref={fileInput}
          type="file"
          className={styles.file}
          aria-label="Фото из галереи"
          accept={ACCEPT}
          onChange={(e) => {
            choose(e.target.files?.[0]);
            e.target.value = '';
          }}
        />
        {url && broken ? (
          <p className={styles.text}>Здесь фото не показать — загрузи его, а точку выберешь потом</p>
        ) : null}
        {url && !broken ? (
          <>
            <p className={styles.text}>Тапни на главное</p>
            <div className={styles.stageWrap}>
              <div
                className={styles.stage}
                tabIndex={0}
                role="group"
                aria-label="Точка фокуса"
                onClick={(e) => {
                  const next = focusFromTap(e.clientX, e.clientY, e.currentTarget.getBoundingClientRect());
                  if (next) setFocus(next);
                }}
                onKeyDown={nudge}
              >
                <img
                  className={styles.photo}
                  src={url}
                  alt=""
                  // HEIC in Android WebView: no preview, so no point to tap; the upload goes with the centre.
                  onError={() => {
                    setBroken(true);
                    setFocus(CENTER);
                  }}
                />
                <span
                  className={styles.marker}
                  style={{ left: `${focus.x * 100}%`, top: `${focus.y * 100}%` }}
                  aria-hidden="true"
                />
              </div>
            </div>
            <div className={styles.crops}>
              {CROPS.map((crop) => (
                <figure key={crop.name} className={styles.crop} aria-label={crop.name}>
                  <div className={styles.frame} style={{ aspectRatio: crop.ratio }}>
                    <img src={url} alt="" style={{ objectPosition: objectPosition(focus) }} />
                  </div>
                  <figcaption className={styles.caption}>{crop.name}</figcaption>
                </figure>
              ))}
            </div>
          </>
        ) : null}
        {error ? (
          <p className={styles.error} role="alert">
            {error}
          </p>
        ) : null}
        <div className={styles.actions}>
          <Button variant="secondary" wide onClick={() => fileInput.current?.click()}>
            {url ? 'Другое фото' : 'Выбрать фото'}
          </Button>
          <Button wide loading={busy} onClick={() => void done()}>
            Готово
          </Button>
          <Button variant="link" wide onClick={onClose}>
            Закрыть
          </Button>
        </div>
      </div>
    </div>
  );
}
