"""Fictional seed data for Bayview Family Clinic. Every name, number and address is made up."""

from datetime import date
from typing import TypedDict


class DoctorSeed(TypedDict):
    id: str
    name: str
    specialty: str
    color: str


class ClinicInfoSeed(TypedDict):
    topic: str
    question: str
    answer: str


class PatientSeed(TypedDict):
    full_name: str
    date_of_birth: date
    phone: str


PEDIATRICS_DOCTOR_ID = "dr-cruz"

DOCTORS: list[DoctorSeed] = [
    {"id": "dr-reyes", "name": "Dr. Ana Reyes", "specialty": "Family medicine", "color": "#2563eb"},
    {
        "id": PEDIATRICS_DOCTOR_ID,
        "name": "Dr. Paolo Cruz",
        "specialty": "Pediatrics",
        "color": "#16a34a",
    },
    {
        "id": "dr-santos",
        "name": "Dr. Lea Santos",
        "specialty": "Internal medicine",
        "color": "#9333ea",
    },
]

CLINIC_INFO: list[ClinicInfoSeed] = [
    {
        "topic": "hours",
        "question": "What are your clinic hours?",
        "answer": "We are open Monday to Saturday, 9 AM to 5 PM, closed for lunch from 12 to 1 PM. "
        "We are closed on Sundays.",
    },
    {
        "topic": "hours",
        "question": "Do you accept walk-ins?",
        "answer": "We see patients by appointment. Walk-ins are seen only if a slot is free, "
        "so booking ahead is best.",
    },
    {
        "topic": "location",
        "question": "Where is the clinic?",
        "answer": "Bayview Family Clinic is at 18 Harbor Lane, Bayview District. "
        "It's on the second floor, above the pharmacy, with parking at the back.",
    },
    {
        "topic": "services",
        "question": "What services do you offer?",
        "answer": "We offer general consults, follow-up visits, pediatric consults for children, "
        "and annual check-ups for adults.",
    },
    {
        "topic": "services",
        "question": "Do you do lab tests or X-rays?",
        "answer": "We don't run lab tests or X-rays on site. The doctor can give you a request "
        "for a partner laboratory nearby.",
    },
    {
        "topic": "doctors",
        "question": "Who are your doctors?",
        "answer": "Dr. Ana Reyes does family medicine, Dr. Paolo Cruz is our pediatrician for "
        "children, and Dr. Lea Santos does internal medicine for adults.",
    },
    {
        "topic": "prices",
        "question": "How much is a consultation?",
        "answer": "A general consult or follow-up is 600 pesos, a pediatric consult is 700 pesos, "
        "and an annual check-up is 1,500 pesos.",
    },
    {
        "topic": "prices",
        "question": "Do you accept insurance or HMO?",
        "answer": "We accept most major HMO cards. Please bring your card and a valid ID "
        "to your visit.",
    },
    {
        "topic": "preparation",
        "question": "How should I prepare for my visit?",
        "answer": "Please arrive 10 minutes early and bring a valid ID, your HMO card if you have "
        "one, and a list of any medicines you take.",
    },
    {
        "topic": "preparation",
        "question": "Do I need to fast for an annual check-up?",
        "answer": "The doctor will tell you if any test needs fasting. For the check-up visit "
        "itself, you don't need to fast.",
    },
    {
        "topic": "other",
        "question": "Is this a real clinic?",
        "answer": "No. Bayview Family Clinic is a demo clinic. Please use made-up details "
        "and don't share real medical information.",
    },
]

SEED_PATIENTS: list[PatientSeed] = [
    {"full_name": "Maria Dela Cruz", "date_of_birth": date(1988, 4, 12), "phone": "09170000101"},
    {"full_name": "Jose Mercado", "date_of_birth": date(1975, 9, 3), "phone": "09170000102"},
    {"full_name": "Angela Bautista", "date_of_birth": date(1992, 1, 27), "phone": "09170000103"},
    {"full_name": "Ramon Villanueva", "date_of_birth": date(1960, 11, 15), "phone": "09170000104"},
    {"full_name": "Carmela Ocampo", "date_of_birth": date(2001, 6, 8), "phone": "09170000105"},
    {"full_name": "Miguel Tan", "date_of_birth": date(2018, 2, 20), "phone": "09170000106"},
    {"full_name": "Liza Navarro", "date_of_birth": date(1983, 7, 30), "phone": "09170000107"},
    {"full_name": "Paolo Garcia", "date_of_birth": date(2015, 12, 5), "phone": "09170000108"},
    {"full_name": "Teresa Lim", "date_of_birth": date(1956, 3, 19), "phone": "09170000109"},
    {"full_name": "Daniel Aquino", "date_of_birth": date(1997, 10, 1), "phone": "09170000110"},
    {"full_name": "Grace Mendoza", "date_of_birth": date(1979, 5, 23), "phone": "09170000111"},
    {"full_name": "Sofia Ramos", "date_of_birth": date(2020, 8, 14), "phone": "09170000112"},
]
