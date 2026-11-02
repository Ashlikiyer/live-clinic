import type { DoctorId, FormField, VisitType } from "@/realtime/events";

export interface Doctor {
  id: DoctorId;
  name: string;
  specialty: string;
  color: string;
}

export const CLINIC_NAME = "Bayview Family Clinic";

/** Mirrors backend/seed/data.py until GET /api/clinic is wired up. */
export const DOCTORS: Doctor[] = [
  { id: "dr-reyes", name: "Dr. Ana Reyes", specialty: "Family medicine", color: "#2563eb" },
  { id: "dr-cruz", name: "Dr. Paolo Cruz", specialty: "Pediatrics", color: "#16a34a" },
  { id: "dr-santos", name: "Dr. Lea Santos", specialty: "Internal medicine", color: "#9333ea" },
];

export const OPEN_MINUTES = 9 * 60;
export const CLOSE_MINUTES = 17 * 60;
export const LUNCH_START_MINUTES = 12 * 60;
export const LUNCH_END_MINUTES = 13 * 60;
export const SLOT_MINUTES = 30;
export const SLOTS_PER_DAY = (CLOSE_MINUTES - OPEN_MINUTES) / SLOT_MINUTES;

export const VISIT_LABELS: Record<VisitType, string> = {
  general_consult: "General consult",
  follow_up: "Follow-up",
  pediatric_consult: "Pediatric consult",
  annual_checkup: "Annual check-up",
};

export const FORM_FIELDS: { field: FormField; label: string; required?: boolean }[] = [
  { field: "full_name", label: "Full name", required: true },
  { field: "date_of_birth", label: "Date of birth", required: true },
  { field: "phone", label: "Phone", required: true },
  { field: "reason", label: "Reason for visit", required: true },
  { field: "symptoms", label: "Symptoms" },
  { field: "symptom_duration", label: "Symptom duration" },
  { field: "allergies", label: "Allergies" },
  { field: "insurance", label: "Insurance (optional)" },
  { field: "preferred_doctor", label: "Preferred doctor" },
];

export function doctorById(id: DoctorId): Doctor | undefined {
  return DOCTORS.find((d) => d.id === id);
}
