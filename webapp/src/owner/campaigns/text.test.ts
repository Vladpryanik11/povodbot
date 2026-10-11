import { describe, expect, it } from 'vitest';
import {
  fillPlaceholders,
  hasPlaceholders,
  htmlToMarkup,
  markupToHtml,
  telegramLength,
  textLimit,
  visibleText,
} from './text';

describe('markupToHtml', () => {
  it('escapes what Telegram rejects bare', () => {
    expect(markupToHtml('a < b && c > d')).toBe('a &lt; b &amp;&amp; c &gt; d');
    expect(markupToHtml('<b>x</b>')).toBe('&lt;b&gt;x&lt;/b&gt;');
  });

  it('turns markers into bold, italic and links', () => {
    expect(markupToHtml('**Кино** и __вино__ [тут](https://povod.club/a?b=1&c=2)')).toBe(
      '<b>Кино</b> и <i>вино</i> <a href="https://povod.club/a?b=1&amp;c=2">тут</a>',
    );
  });

  it('nests a link inside bold', () => {
    expect(markupToHtml('**[тут](https://a.ru)**')).toBe('<b><a href="https://a.ru">тут</a></b>');
  });

  it('leaves crossing, unclosed and empty markers as text', () => {
    expect(markupToHtml('**a __b** c__')).toBe('**a <i>b** c</i>');
    expect(markupToHtml('**жирный')).toBe('**жирный');
    expect(markupToHtml('****')).toBe('****');
  });

  it('keeps a non-https link as text', () => {
    expect(markupToHtml('[x](http://a.ru)')).toBe('[x](http://a.ru)');
  });
});

describe('htmlToMarkup', () => {
  it.each([
    '<b>Кино</b> &amp; <i>вино</i>',
    '<a href="https://a.ru/?x=1&amp;y=2">тут</a>',
    'a &lt; b',
    '{date} у нас «{event}». Билеты уже можно взять.',
  ])('round-trips %s', (html) => {
    expect(markupToHtml(htmlToMarkup(html))).toBe(html);
  });

  it('decodes numeric entities', () => {
    expect(htmlToMarkup('&#128512; &#x41;')).toBe('😀 A');
  });
});

describe('length', () => {
  it('counts the visible text in UTF-16 units', () => {
    expect(visibleText('<b>Кино</b> &amp; 😀')).toBe('Кино & 😀');
    expect(telegramLength('<b>Кино</b> &amp; 😀')).toBe(9);
  });

  it('an emoji at the edge goes over the caption limit', () => {
    const html = markupToHtml('a'.repeat(1023) + '😀');
    expect(telegramLength(html)).toBe(1025);
    expect(telegramLength(html)).toBeGreaterThan(textLimit('event'));
    expect(telegramLength(html)).toBeGreaterThan(textLimit('upload'));
    expect(telegramLength(html)).toBeLessThan(textLimit('none'));
  });
});

describe('placeholders', () => {
  it('fills the event and its Moscow date', () => {
    expect(
      fillPlaceholders('{date} у нас «{event}»', {
        title: 'Кино на крыше',
        startsAt: '2026-10-18T16:00:00Z',
      }),
    ).toBe('18 октября у нас «Кино на крыше»');
  });

  it('uses the Moscow day near midnight', () => {
    expect(fillPlaceholders('{date}', { title: '', startsAt: '2026-10-18T21:30:00Z' })).toBe(
      '19 октября',
    );
  });

  it('finds what is left to fill', () => {
    expect(hasPlaceholders('Завтра «{event}»')).toBe(true);
    expect(hasPlaceholders('Завтра «Кино»')).toBe(false);
  });
});
