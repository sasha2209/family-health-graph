import { useColorScheme } from 'react-native';

import type { Level } from './types';

const light = {
  bg: '#F7F7F5',
  surface: '#FFFFFF',
  text: '#1D1D1B',
  muted: '#6B6B66',
  border: '#E3E2DC',
  accent: '#2F6F62',
  accentInk: '#FFFFFF',
  danger: '#B4442F',
  level: {
    high: { fg: '#B4442F', bg: '#FBEEEA' },
    moderate: { fg: '#9A6A12', bg: '#FBF3E2' },
    info: { fg: '#3D6191', bg: '#ECF1F8' },
  } as Record<Level, { fg: string; bg: string }>,
};

const dark: typeof light = {
  bg: '#161715',
  surface: '#1F201E',
  text: '#ECEBE6',
  muted: '#A09F98',
  border: '#33342F',
  accent: '#5FB3A1',
  accentInk: '#0D1A17',
  danger: '#F08A74',
  level: {
    high: { fg: '#F08A74', bg: '#3A2420' },
    moderate: { fg: '#E2B45C', bg: '#362C19' },
    info: { fg: '#8FB0E0', bg: '#1F2A3A' },
  },
};

export type Palette = typeof light;

export function usePalette(): Palette {
  return useColorScheme() === 'dark' ? dark : light;
}

export const LEVEL_LABEL: Record<Level, string> = {
  high: 'Discuss soon',
  moderate: 'Next visit',
  info: 'Good to know',
};
