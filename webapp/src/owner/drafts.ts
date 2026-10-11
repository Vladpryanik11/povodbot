import type { EventForm } from './form';

/** Unsaved form input kept in memory, so it survives a trip to «Как видит гость». Key: event id or 'new'. */
export class DraftStore {
  private readonly forms = new Map<string, EventForm>();

  get(key: string): EventForm | undefined {
    return this.forms.get(key);
  }

  set(key: string, form: EventForm): void {
    this.forms.set(key, form);
  }

  clear(key: string): void {
    this.forms.delete(key);
  }
}
