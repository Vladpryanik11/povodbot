import { Clapperboard, Dices, MessagesSquare, PartyPopper, type LucideIcon } from 'lucide-react';
import type { DirectionIcon } from '../api/types';

export const DIRECTION_ICONS: Record<DirectionIcon, LucideIcon> = {
  film: Clapperboard,
  dice: Dices,
  talk: MessagesSquare,
  party: PartyPopper,
};

export const ICON_STROKE = 1.75;
