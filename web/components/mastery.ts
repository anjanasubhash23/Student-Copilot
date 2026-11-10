// One sequential blue ramp for p_known (CSS variables --m0..--m5, stepped separately for dark mode);
// unassessed topics are neutral grey. Mastery is also marked with a ✓, never by colour alone.

export const MASTERED = 0.95;

export function masteryVar(p: number, assessed: boolean): string {
  if (!assessed) return "var(--unassessed)";
  const step = p >= MASTERED ? 5 : Math.min(4, Math.floor(p * 5));
  return `var(--m${step})`;
}

export function pct(p: number): string {
  return `${Math.round(p * 100)}%`;
}

export const LEGEND: { label: string; color: string }[] = [
  { label: "not assessed", color: "var(--unassessed)" },
  { label: "0–20%", color: "var(--m0)" },
  { label: "40%", color: "var(--m2)" },
  { label: "80%", color: "var(--m4)" },
  { label: "mastered ✓", color: "var(--m5)" },
];
