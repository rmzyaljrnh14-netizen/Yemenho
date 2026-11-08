// Arabic labels for the quality & patient-safety modules (v0.7).
// The backend decides on stable codes; the portal only turns them into words.

export const INCIDENT_TYPE_AR: Record<string, string> = {
  medication: "دواء",
  fall: "سقوط",
  pressure_ulcer: "قرحة ضغط",
  infection: "عدوى",
  surgical: "جراحي",
  diagnostic: "تشخيصي",
  transfusion: "نقل دم",
  equipment: "أجهزة",
  behaviour: "سلوكي",
  other: "أخرى",
};

export const SEVERITY_AR: Record<string, string> = {
  near_miss: "شبه حادث",
  minor: "خفيف",
  moderate: "متوسط",
  major: "جسيم",
  catastrophic: "كارثي",
};

export const PATIENT_HARM_AR: Record<string, string> = {
  none: "لا ضرر",
  mild: "ضرر بسيط",
  moderate: "ضرر متوسط",
  severe: "ضرر شديد",
  death: "وفاة",
};

export const INCIDENT_STATUS_AR: Record<string, string> = {
  reported: "مُبلَّغ",
  under_review: "قيد المراجعة",
  rca: "تحليل الأسباب",
  capa: "إجراءات تصحيحية",
  closed: "مغلق",
  rejected: "مرفوض",
};

export const RCA_STATUS_AR: Record<string, string> = {
  open: "مفتوح",
  in_progress: "قيد التنفيذ",
  completed: "مكتمل",
  cancelled: "ملغى",
};

export const RCA_METHOD_AR: Record<string, string> = {
  five_whys: "الأسباب الخمسة",
  fishbone: "عظمة السمكة",
  fault_tree: "شجرة الأعطال",
  other: "أخرى",
};

export const RCA_CATEGORY_AR: Record<string, string> = {
  patient: "المريض",
  staff: "الكوادر",
  communication: "التواصل",
  equipment: "الأجهزة",
  environment: "البيئة",
  process: "العمليات",
  management: "الإدارة",
  training: "التدريب",
  other: "أخرى",
};

export const CAPA_STATUS_AR: Record<string, string> = {
  open: "مفتوح",
  in_progress: "قيد التنفيذ",
  done: "منجز",
  verified: "مُتحقَّق منه",
  cancelled: "ملغى",
};

export const CAPA_KIND_AR: Record<string, string> = {
  corrective: "تصحيحي",
  preventive: "وقائي",
};

export const PRIORITY_AR: Record<string, string> = {
  low: "منخفضة",
  medium: "متوسطة",
  high: "عالية",
  critical: "حرجة",
};

export const RISK_CATEGORY_AR: Record<string, string> = {
  clinical: "سريري",
  medication: "دوائي",
  infection: "عدوى",
  environment: "بيئي",
  equipment: "أجهزة",
  staffing: "كوادر",
  information: "معلومات",
  security: "أمني",
  other: "أخرى",
};

export const RISK_STATUS_AR: Record<string, string> = {
  open: "مفتوح",
  mitigated: "مُخفَّف",
  accepted: "مقبول",
  closed: "مغلق",
};

export const AUDIT_STATUS_AR: Record<string, string> = {
  planned: "مخطط",
  in_progress: "قيد التنفيذ",
  completed: "مكتمل",
  closed: "مغلق",
};

export const PLAN_STATUS_AR: Record<string, string> = {
  draft: "مسودة",
  active: "نشطة",
  completed: "مكتملة",
  cancelled: "ملغاة",
};

export const ACTION_STATUS_AR: Record<string, string> = {
  open: "مفتوح",
  in_progress: "قيد التنفيذ",
  done: "منجز",
  cancelled: "ملغى",
};

export const DOC_TYPE_AR: Record<string, string> = {
  policy: "سياسة",
  procedure: "إجراء",
  guideline: "دليل إرشادي",
  form: "نموذج",
  record: "سجل",
  other: "أخرى",
};

export const DOC_STATUS_AR: Record<string, string> = {
  draft: "مسودة",
  under_review: "قيد المراجعة",
  approved: "معتمدة",
  obsolete: "ملغاة",
};

export const MEETING_STATUS_AR: Record<string, string> = {
  scheduled: "مجدول",
  held: "منعقد",
  cancelled: "ملغى",
};

export const SEVERITY_TONE: Record<string, "on" | "warn" | "bad" | "off"> = {
  near_miss: "off",
  minor: "on",
  moderate: "warn",
  major: "bad",
  catastrophic: "bad",
};

export function label(map: Record<string, string>, code: string | null | undefined): string {
  if (!code) return "—";
  return map[code] ?? code;
}

// Risk score band (likelihood × impact, 1..25).
export function riskBand(score: number): { label: string; tone: "on" | "warn" | "bad" } {
  if (score >= 15) return { label: "مرتفع", tone: "bad" };
  if (score >= 8) return { label: "متوسط", tone: "warn" };
  return { label: "منخفض", tone: "on" };
}

export function fmtDate(value: string | null | undefined): string {
  if (!value) return "—";
  return value.slice(0, 10);
}
