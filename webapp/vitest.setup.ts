import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// jsdom has no object URLs; the owner mock and the poster sheet make them for picked photos.
let objectUrls = 0;
URL.createObjectURL ??= () => `blob:mock/${++objectUrls}`;
URL.revokeObjectURL ??= () => {};

afterEach(() => {
  cleanup();
  localStorage.clear();
});
