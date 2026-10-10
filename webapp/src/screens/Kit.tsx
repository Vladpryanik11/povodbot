import { useState } from 'react';
import { Ticket } from 'lucide-react';
import { buildFixtures } from '../api/mock/fixtures';
import { formatDateTime, formatPrice, seatsLabel } from '../lib/format';
import { Button } from '../ui/Button';
import { Dialog } from '../ui/Dialog';
import { DirectionTile } from '../ui/DirectionTile';
import { EmptyState } from '../ui/EmptyState';
import { ErrorState } from '../ui/ErrorState';
import { Pill } from '../ui/Pill';
import { Poster } from '../ui/Poster';
import { Skeleton } from '../ui/Skeleton';
import { Stepper } from '../ui/Stepper';
import styles from './Kit.module.css';

const data = buildFixtures(Date.now());

/** Dev-only showcase of every kit component in its states (route #/kit). */
export function Kit() {
  const [theme, setTheme] = useState(document.documentElement.dataset.theme ?? 'dark');
  const [count, setCount] = useState(2);
  const [dialog, setDialog] = useState(false);
  const [selected, setSelected] = useState('d-film');
  const film = data.events[0];

  const toggle = () => {
    const next = theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    setTheme(next);
  };

  return (
    <div className={styles.page}>
      <header className={styles.row}>
        <h1 className="t-h1">Кит</h1>
        <Button variant="outline" onClick={toggle}>
          Тема: {theme}
        </Button>
      </header>

      <section className={styles.section}>
        <h2 className="t-h2">Постеры</h2>
        <Poster poster={film.poster} title={film.title} ratio="2:1" icon="film">
          <div className={styles.row}>
            <Pill tone="accent">{formatDateTime(film.startsAt, film.timezone)}</Pill>
          </div>
          <div>
            <div className="t-display">Киновечер</div>
            <div className={styles.row}>
              <Pill tone="glass">{seatsLabel(film.seatsLeft)}</Pill>
              <Pill tone="glass">от {formatPrice(155000)}</Pill>
            </div>
          </div>
        </Poster>
        <div className={styles.grid}>
          <Poster poster={null} title="Настолки до утра" ratio="4:5" icon="dice">
            <span />
            <span className="t-h3">Настолки до утра</span>
          </Poster>
          <Poster poster={data.events[3].poster} title={data.events[3].title} ratio="4:5" icon="party">
            <span />
            <span className="t-h3">{data.events[3].title}</span>
          </Poster>
        </div>
      </section>

      <section className={styles.section}>
        <h2 className="t-h2">Направления</h2>
        <div className={styles.row}>
          {data.directions.map((d) => (
            <DirectionTile key={d.id} direction={d} selected={selected === d.id} onSelect={() => setSelected(d.id)} />
          ))}
        </div>
      </section>

      <section className={styles.section}>
        <h2 className="t-h2">Пилюли</h2>
        <div className={styles.row}>
          <Pill tone="accent">пт, 16 окт</Pill>
          <Pill tone="success">Действителен</Pill>
          <Pill tone="warning">осталось 2 места</Pill>
          <Pill tone="error">мест нет</Pill>
          <Pill tone="muted">Возвращён</Pill>
        </div>
      </section>

      <section className={styles.section}>
        <h2 className="t-h2">Кнопки и счётчик</h2>
        <Button wide>Оплатить 3 100 ₽</Button>
        <Button wide loading>
          Оплатить 3 100 ₽
        </Button>
        <Button wide disabled>
          Выберите билеты
        </Button>
        <div className={styles.row}>
          <Button variant="outline" onClick={() => setDialog(true)}>
            Открыть диалог
          </Button>
          <Button variant="link">Отменить бронь</Button>
        </div>
        <div className={styles.between}>
          <span>
            Входной
            <br />
            <span className={styles.muted}>1 550 ₽</span>
          </span>
          <Stepper value={count} max={5} label="Входной" onChange={setCount} />
        </div>
        <div className={styles.between}>
          <span>На максимуме</span>
          <Stepper value={2} max={2} label="С другом" onChange={() => undefined} />
        </div>
      </section>

      <section className={`${styles.section} glass ${styles.glassCard}`}>
        <h2 className="t-h3">Стеклянная карточка</h2>
        <p className={styles.muted}>Текст на стекле держит контраст и без размытия.</p>
      </section>

      <section className={styles.section}>
        <h2 className="t-h2">Состояния</h2>
        <Skeleton height={120} />
        <EmptyState
          icon={Ticket}
          title="Билетов пока нет"
          text="Выберите вечер в афише — билеты появятся здесь."
          action={{ label: 'Открыть афишу', onClick: () => undefined }}
        />
        <ErrorState
          title="Нет связи"
          text="Проверьте интернет. Оплаченные билеты никуда не денутся."
          actionLabel="Повторить"
          onAction={() => undefined}
        />
      </section>

      {dialog ? (
        <Dialog
          title="Отменить бронь?"
          text="Места вернутся в продажу."
          confirmLabel="Отменить"
          cancelLabel="Оставить"
          onConfirm={() => setDialog(false)}
          onCancel={() => setDialog(false)}
        />
      ) : null}
    </div>
  );
}
