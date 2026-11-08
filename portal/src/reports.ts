import type { AssessmentStatus, PeriodStatus } from "./types";

export const MONTHS_AR = [
  "يناير",
  "فبراير",
  "مارس",
  "أبريل",
  "مايو",
  "يونيو",
  "يوليو",
  "أغسطس",
  "سبتمبر",
  "أكتوبر",
  "نوفمبر",
  "ديسمبر",
];

export const STATUS_AR: Record<PeriodStatus, string> = {
  draft: "مسودة",
  submitted: "مُرسلة للمراجعة",
  reviewed: "مراجَعة",
  approved: "معتمدة",
  returned: "مُعادة للتعديل",
};

export const ASSESSMENT_AR: Record<AssessmentStatus, string> = {
  good: "محقق للهدف",
  warning: "دون الهدف",
  poor: "خارج الحدود",
  unknown: "غير محسوب",
};

export function statusLabel(status: PeriodStatus | null | undefined): string {
  return status ? STATUS_AR[status] : "لا توجد فترة";
}

export function assessmentBadgeClass(status: AssessmentStatus): string {
  if (status === "good") return "badge on";
  if (status === "warning") return "badge warn";
  if (status === "poor") return "badge off";
  return "badge";
}

export function movementLabel(movement: string, improving: boolean | null): string {
  if (movement === "unknown") return "لا مقارنة";
  if (movement === "flat") return "مستقر";
  if (improving === true) return "تحسّن";
  if (improving === false) return "تراجع";
  return movement === "up" ? "ارتفاع" : "انخفاض";
}

export function movementArrow(movement: string): string {
  if (movement === "up") return "▲";
  if (movement === "down") return "▼";
  if (movement === "flat") return "▬";
  return "—";
}

export function complianceColor(percent: number | null): string {
  if (percent === null) return "#94a3b8";
  if (percent >= 85) return "#15803d";
  if (percent >= 70) return "#b45309";
  return "#b91c1c";
}

export function formatNumber(value: number | null | undefined, digits = 2): string {
  if (value === null || value === undefined) return "—";
  const rounded = Number(value.toFixed(digits));
  return String(rounded);
}

export function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${formatNumber(value, 1)}%`;
}

export function currentYear(): number {
  return new Date().getFullYear();
}

export function currentMonth(): number {
  return new Date().getMonth() + 1;
}
