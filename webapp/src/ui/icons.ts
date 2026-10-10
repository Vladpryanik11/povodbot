import { BookOpen, Clapperboard, Palette, type LucideIcon } from 'lucide-react';
import type { DirectionIcon } from '../api/types';

export const DIRECTION_ICONS: Record<DirectionIcon, LucideIcon> = {
  film: Clapperboard,
  workshop: Palette,
  book: BookOpen,
};

export const ICON_STROKE = 1.75;
