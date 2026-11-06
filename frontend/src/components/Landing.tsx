"use client";

import Image from "next/image";
import { useEffect, useState, useSyncExternalStore } from "react";

import { API_URL } from "@/lib/api";
import { BUSY_NOTICE } from "@/lib/busy";
import { Orb } from "@/components/call/Orb";
import { CLINIC_NAME, DOCTORS } from "@/lib/clinic";
import { DEFAULT_VOICE, VOICE_CHOICES, parseVoiceChoice, type VoiceChoice } from "@/voice/choice";
import { loadKokoro, onKokoroStatus, type KokoroStatus } from "@/voice/tts";

import heroPhoto from "../../public/hero-caller.jpg";

const VOICE_KEY = "mia-voice";

type BackendState = "waking" | "ready" | "busy" | "offline";

/** While Mia's line is busy, look again this often: Groq's limits clear within minutes. */
const BUSY_RECHECK_MS = 30_000;

/** Wakes the backend (Render free tier sleeps) as soon as the landing page opens, and says
 * whether Mia's line is busy (Groq's free tier at its limit). */
function useBackendWake(): BackendState {
  const [state, setState] = useState<BackendState>("waking");
  const [check, setCheck] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 60_000);
    let recheck: ReturnType<typeof setTimeout> | undefined;
    fetch(`${API_URL}/api/health`, { signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) return setState("offline");
        const body = (await res.json().catch(() => ({}))) as { llm?: string };
        if (body.llm === "busy") {
          setState("busy");
          recheck = setTimeout(() => setCheck((n) => n + 1), BUSY_RECHECK_MS);
        } else {
          setState("ready");
        }
      })
      .catch(() => setState("offline"))
      .finally(() => clearTimeout(timeout));
    return () => {
      clearTimeout(timeout);
      clearTimeout(recheck);
      controller.abort();
    };
  }, [check]);
  return state;
}

/** Downloads and warms up Kokoro only when it's the chosen voice (cached after the first time). */
function useVoiceModel(enabled: boolean): KokoroStatus {
  const [status, setStatus] = useState<KokoroStatus>({ state: "loading", progress: 0 });
  useEffect(() => {
    if (!enabled) return;
    const unsubscribe = onKokoroStatus(setStatus);
    loadKokoro().catch(() => undefined);
    return unsubscribe;
  }, [enabled]);
  return status;
}

// The caller's voice choice, remembered in this browser. Kept in memory too, so choosing still
// works when storage is blocked.
let chosenVoice: VoiceChoice | null = null;
const voiceListeners = new Set<() => void>();

function readVoiceChoice(): VoiceChoice {
  if (chosenVoice) return chosenVoice;
  try {
    return parseVoiceChoice(localStorage.getItem(VOICE_KEY));
  } catch {
    return DEFAULT_VOICE;
  }
}

function useVoiceChoice(): [VoiceChoice, (choice: VoiceChoice) => void] {
  const choice = useSyncExternalStore(
    (listener) => {
      voiceListeners.add(listener);
      return () => voiceListeners.delete(listener);
    },
    readVoiceChoice,
    () => DEFAULT_VOICE,
  );
  const choose = (next: VoiceChoice) => {
    chosenVoice = next;
    try {
      localStorage.setItem(VOICE_KEY, next);
    } catch {
      // Storage blocked: the choice lasts until the page closes.
    }
    voiceListeners.forEach((listener) => listener());
  };
  return [choice, choose];
}

const BACKEND_LABEL: Record<BackendState, string> = {
  waking: "Waking up the clinic...",
  ready: "Clinic line is open",
  busy: BUSY_NOTICE,
  offline: "The clinic is offline right now. You can still watch a demo call.",
};

const NAV = [
  { href: "#top", label: "Home" },
  { href: "#how", label: "How it works" },
  { href: "#doctors", label: "Doctors" },
  { href: "#faq", label: "FAQ" },
];

const FAQS = [
  {
    q: "Is this a real clinic?",
    a: "No. Bayview Family Clinic is fictional and every booking lives in your own private sandbox. Use made-up details.",
  },
  {
    q: "Can Mia give me medical advice?",
    a: "No. Mia can book visits and answer questions about hours, services and prices. Anything medical is for the doctor at your visit.",
  },
  {
    q: "What if it is an emergency?",
    a: "If you mention signs like chest pain or trouble breathing, Mia stops booking and tells you to call 911 or go to the nearest emergency room.",
  },
  {
    q: "Can I speak Tagalog?",
    a: "Yes. Speak English, Tagalog or Taglish, and Mia answers the same way.",
  },
  {
    q: "Is my voice recorded?",
    a: "Your audio is transcribed and not stored. Transcripts and form details are deleted after 24 hours.",
  },
  {
    q: "Can I talk to a person instead?",
    a: "Yes. Ask for the front desk at any time and Mia will transfer you.",
  },
];

const SAFETY = [
  ["No medical advice.", "Mia never diagnoses or suggests medicine. That's for your doctor."],
  ["Emergencies come first.", "Chest pain or trouble breathing? She tells you to call 911 right away."],
  ["Nothing booked without a yes.", "She reads every detail back before changing your appointment."],
];

const CLINIC_FACTS = [
  ["Hours", "Mon–Sat\n9:00 AM–5:00 PM"],
  ["Visits", "Consults, follow-ups, check-ups"],
  ["Booking window", "Up to 14 days ahead"],
  ["Need a person?", "Ask Mia to transfer you"],
];

const initials = (name: string) =>
  name
    .replace(/^Dr\.\s*/, "")
    .split(/\s+/)
    .map((part) => part[0])
    .join("")
    .slice(0, 2);

function Pill({ tag, start, children }: { tag: string; start?: boolean; children: React.ReactNode }) {
  return (
    <span className={`inline-flex items-center gap-2 ${start ? "self-start" : "self-center"} whitespace-nowrap rounded-full border border-line py-1 pl-1 pr-3 text-[12.5px] text-ink-soft`}>
      <span className="rounded-full bg-rose-soft px-2.5 py-0.5 font-medium text-rose-ink">{tag}</span>
      {children}
    </span>
  );
}

function Logo() {
  return (
    <span className="flex items-center gap-2.5">
      <span className="grid size-[26px] place-items-center rounded-full bg-ink">
        <span className="size-2 rounded-full bg-white" />
      </span>
      <span className="text-[19px] font-semibold tracking-[-0.02em]">Bayview</span>
    </span>
  );
}

const primaryButton =
  "flex-none whitespace-nowrap rounded-full bg-brand font-medium tracking-[0.04em] text-brand-ink transition-colors hover:bg-brand-hover disabled:cursor-not-allowed disabled:opacity-50";
const secondaryButton =
  "flex-none whitespace-nowrap rounded-full border border-line-strong bg-surface font-medium tracking-[0.04em] text-ink transition-colors hover:bg-surface-muted disabled:cursor-not-allowed disabled:opacity-50";

export function Landing({
  onCall,
  onDemo,
}: {
  onCall: (voice: VoiceChoice, options?: { typing?: boolean }) => void;
  onDemo: () => void;
}) {
  const backend = useBackendWake();
  const [choice, setChoice] = useVoiceChoice();
  const voice = useVoiceModel(choice === "kokoro");
  const [openFaq, setOpenFaq] = useState<number | null>(0);
  const offline = backend === "offline";
  const call = () => onCall(choice);

  return (
    <div className="bg-surface">
      <div className="mx-auto max-w-[1240px] border-x border-line">
        <nav className="flex flex-wrap items-center justify-between gap-5 border-b border-line px-8 py-5 max-sm:px-4">
          <Logo />
          <div className="flex max-w-full gap-0.5 overflow-x-auto rounded-full border border-line p-1 text-[13.5px]">
            {NAV.map((item, i) => (
              <a
                key={item.href}
                href={item.href}
                className={`whitespace-nowrap rounded-full px-4 py-[7px] ${
                  i === 0 ? "bg-ink text-white" : "text-ink-muted hover:text-ink"
                }`}
              >
                {item.label}
              </a>
            ))}
          </div>
          <button
            type="button"
            onClick={call}
            disabled={offline}
            className={`${primaryButton} flex h-[42px] items-center gap-2.5 px-5 text-[13px]`}
          >
            CALL THE CLINIC <span className="text-[15px]" aria-hidden>↗</span>
          </button>
        </nav>

        <section id="top" className="grid min-h-[600px] grid-cols-[repeat(auto-fit,minmax(min(100%,440px),1fr))]">
          <div className="flex flex-col justify-center gap-7 px-8 pb-12 pt-16 max-sm:px-4">
            <Pill tag="Demo" start>
              Fictional clinic · uses fake data only
            </Pill>
            <h1 className="text-balance text-[clamp(46px,6vw,76px)] font-medium leading-none tracking-[-0.045em]">
              Call the clinic. Mia books it while you talk.
            </h1>
            <p className="max-w-[460px] text-pretty text-[17px] leading-[1.55] text-ink-muted">
              Speak naturally to Bayview&apos;s voice receptionist. Watch your appointment land on
              the calendar and your intake form fill itself in as you speak.
            </p>
            <div className="flex flex-wrap gap-2.5">
              <button type="button" onClick={call} disabled={offline} className={`${primaryButton} h-[52px] px-7 text-[13.5px]`}>
                START A CALL
              </button>
              <button
                type="button"
                onClick={() => onCall(choice, { typing: true })}
                disabled={offline}
                className={`${secondaryButton} h-[52px] px-7 text-[13.5px]`}
              >
                TYPE INSTEAD
              </button>
            </div>

            <fieldset className="flex max-w-[360px] flex-col gap-2">
              <legend className="mb-2 text-xs text-ink-faint">Mia&apos;s voice</legend>
              <div className="grid grid-cols-3 gap-0.5 rounded-full border border-line p-1 text-[13px]">
                {VOICE_CHOICES.map((option) => (
                  <label
                    key={option.value}
                    className={`cursor-pointer rounded-full px-2 py-1.5 text-center font-medium transition-colors has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ink ${
                      choice === option.value ? "bg-ink text-white" : "text-ink-muted hover:text-ink"
                    }`}
                  >
                    <input
                      type="radio"
                      name="voice"
                      value={option.value}
                      checked={choice === option.value}
                      onChange={() => setChoice(option.value)}
                      className="sr-only"
                    />
                    {option.label}
                  </label>
                ))}
              </div>
              <div aria-live="polite" className="text-xs text-ink-faint">
                {choice === "kokoro" && voice.state === "loading" ? (
                  <div className="flex flex-col gap-2">
                    <div className="flex justify-between">
                      <span>Getting Mia&apos;s voice ready</span>
                      <span className="font-mono">{Math.round(voice.progress * 100)}%</span>
                    </div>
                    <div className="h-[3px] overflow-hidden rounded-full bg-line">
                      <div
                        className="h-full bg-ink transition-[width] duration-200"
                        style={{ width: `${Math.round(voice.progress * 100)}%` }}
                      />
                    </div>
                  </div>
                ) : choice === "kokoro" && voice.state === "ready" && voice.tooSlow ? (
                  "This device is a bit slow for the in-browser voice, so Mia will use the built-in one."
                ) : choice === "kokoro" && voice.state === "failed" ? (
                  "The in-browser voice can't run on this device, so Mia will use the built-in one."
                ) : (
                  VOICE_CHOICES.find((option) => option.value === choice)?.hint
                )}
              </div>
            </fieldset>

            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-faint" aria-live="polite">
              <span className="flex items-center gap-2">
                <span
                  className={`size-2 rounded-full ${
                    backend === "ready"
                      ? "bg-live"
                      : backend === "waking"
                        ? "bg-thinking"
                        : backend === "busy"
                          ? "bg-rose"
                          : "bg-ink-ghost"
                  }`}
                />
                {BACKEND_LABEL[backend]}
              </span>
              <button type="button" onClick={onDemo} className="underline-offset-2 hover:text-ink hover:underline">
                Watch a demo call
              </button>
            </div>
          </div>

          <div className="bg-dots relative min-h-[560px] border-l border-line max-[900px]:border-l-0 max-[900px]:border-t">
            <div className="absolute inset-8 overflow-hidden rounded-[28px] max-sm:inset-4">
              <Image
                src={heroPhoto}
                alt="A doctor on the phone at his desk"
                fill
                priority
                sizes="(min-width: 900px) 600px, 100vw"
                className="object-cover contrast-[1.05] grayscale"
              />
              <a
                href="https://unsplash.com/@silverkblack"
                className="absolute bottom-3 left-4 text-[10.5px] text-white/80 hover:text-white"
              >
                Photo by Vitaly Gariev on Unsplash
              </a>
            </div>
            <div className="pointer-events-none absolute left-0 top-[72px] flex items-center gap-3 whitespace-nowrap rounded-full border border-line bg-surface py-2.5 pl-2.5 pr-[18px] shadow-[0_20px_40px_-20px_rgba(0,0,0,.25)]">
              <Orb size={44} mode="hero" />
              <div className="flex flex-col">
                <span className="text-sm font-semibold">Mia is listening</span>
                <span className="text-xs text-ink-faint">Bayview receptionist</span>
              </div>
            </div>
            <div className="pointer-events-none absolute bottom-14 right-14 flex w-[236px] flex-col gap-2.5 rounded-[20px] border border-line bg-surface p-3.5 shadow-[0_20px_40px_-20px_rgba(0,0,0,.25)] max-sm:bottom-8 max-sm:right-8">
              <div className="flex items-center justify-between">
                <span className="text-xs text-ink-faint">Tue, Nov 10</span>
                <span className="rounded-full bg-confirmed px-2.5 py-0.5 text-[11px] font-semibold text-confirmed-ink">
                  Confirmed
                </span>
              </div>
              <div className="text-[22px] font-medium tracking-[-0.03em]">2:30 PM</div>
              <div className="text-[12.5px] text-ink-muted">Dr. Ana Reyes · General consult</div>
            </div>
          </div>
        </section>

        <section id="doctors" className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] border-t border-line">
          <div className="flex flex-col justify-center gap-1.5 px-8 py-7 max-sm:px-4">
            <span className="text-[17px] font-medium leading-tight tracking-[-0.02em]">
              Three doctors.
              <br />
              Mon–Sat, 9 AM–5 PM.
            </span>
            <span className="text-[12.5px] text-ink-faint">Lunch break 12–1 PM</span>
          </div>
          {DOCTORS.map((doctor) => (
            <div key={doctor.id} className="flex items-center gap-3.5 border-l border-line px-6 py-[22px] max-sm:border-l-0 max-sm:border-t">
              <div className="relative grid size-[52px] flex-none place-items-center rounded-full border border-line bg-surface-muted text-[15px] font-semibold tracking-[-0.02em]">
                {initials(doctor.name)}
                <span className="absolute -bottom-0.5 -right-0.5 grid size-5 place-items-center rounded-full border-2 border-white bg-ink text-[13px] leading-none text-white" aria-hidden>
                  +
                </span>
              </div>
              <div className="flex min-w-0 flex-col gap-0.5">
                <span className="text-[14.5px] font-semibold">{doctor.name}</span>
                <span className="text-[12.5px] text-ink-faint">{doctor.specialty}</span>
              </div>
            </div>
          ))}
        </section>

        <section id="how" className="flex flex-col items-center gap-4 border-t border-line px-8 pb-14 pt-20 text-center max-sm:px-4">
          <Pill tag="01">On the call</Pill>
          <h2 className="text-[clamp(34px,4vw,52px)] font-medium leading-[1.05] tracking-[-0.04em]">
            Talk naturally. Watch it happen.
          </h2>
          <p className="max-w-[520px] text-base leading-[1.55] text-ink-muted">
            No menus, no hold music. Mia asks one question at a time and shows her work as she goes.
          </p>
        </section>

        <section className="grid grid-cols-[repeat(auto-fit,minmax(280px,1fr))] border-t border-line">
          <Feature title="Books on a live calendar" body="Offered times light up. Your slot turns yellow while Mia holds it, green once you say yes.">
            <div className="bg-stripes h-[30px] rounded-lg" />
            <div className="flex h-[30px] items-center rounded-lg border border-holding-line bg-holding px-2.5 text-xs font-semibold text-holding-ink">
              Holding · 2:30 PM
            </div>
            <div className="flex h-[30px] items-center rounded-lg border border-confirmed-line bg-confirmed px-2.5 text-xs font-semibold text-confirmed-ink">
              Confirmed · Jamie S.
            </div>
          </Feature>
          <Feature title="Fills your intake form" body="Name, birthday, symptoms: each field fills in the moment you say it. Change your mind and it updates." bordered>
            <div className="flex flex-col gap-0.5 rounded-xl border border-line bg-surface px-3 py-[9px]">
              <span className="text-[11px] text-ink-faint">Full name</span>
              <span className="text-[13.5px] font-medium">Jamie Santos-Lim</span>
            </div>
            <div className="flex flex-col gap-0.5 rounded-xl border border-ink bg-surface px-3 py-[9px] shadow-[0_0_0_4px_rgba(17,17,19,.06)]">
              <span className="flex justify-between text-[11px] text-ink-faint">
                Date of birth<span className="font-medium text-rose-ink">Corrected</span>
              </span>
              <span className="text-[13.5px] font-medium">March 3, 1994</span>
            </div>
          </Feature>
          <Feature title="Stops when you interrupt" body="Cut in any time, like with a real person. Mia stops talking right away and follows your lead." bordered>
            <div className="max-w-[85%] self-start rounded-[4px_14px_14px_14px] bg-surface px-3 py-[9px] text-[13px] leading-snug">
              Tuesday at 9:30 AM with Dr. Reyes, for a{" "}
              <span className="text-[#b5b5b9] line-through">general consult…</span>
            </div>
            <div className="max-w-[85%] self-end rounded-[14px_4px_14px_14px] bg-ink px-3 py-[9px] text-[13px] text-white">
              Actually, can we do the afternoon?
            </div>
          </Feature>
        </section>

        <section className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,420px),1fr))] gap-4 border-t border-line bg-bg p-4">
          <div className="flex flex-col gap-5 rounded-3xl border border-line bg-surface p-8 max-sm:p-6">
            <h3 className="text-[28px] font-medium leading-[1.1] tracking-[-0.035em]">
              Careful with your health,
              <br />
              by design.
            </h3>
            <ol className="flex flex-col">
              {SAFETY.map(([title, body], i) => (
                <li key={title} className="flex gap-4 border-t border-line py-3.5">
                  <span className="pt-0.5 font-mono text-xs font-medium text-ink-ghost">{String(i + 1).padStart(2, "0")}</span>
                  <span className="text-[14.5px] leading-normal">
                    <b className="font-semibold">{title}</b> <span className="text-ink-muted">{body}</span>
                  </span>
                </li>
              ))}
            </ol>
          </div>
          <div className="flex flex-col justify-between gap-6 rounded-3xl bg-surface-sunk p-8 max-sm:p-6">
            <h3 className="text-[28px] font-medium leading-[1.1] tracking-[-0.035em]">{CLINIC_NAME}</h3>
            <dl className="grid grid-cols-2 gap-3">
              {CLINIC_FACTS.map(([label, value]) => (
                <div key={label} className="flex flex-col gap-1 rounded-2xl bg-surface p-4">
                  <dt className="text-xs text-ink-faint">{label}</dt>
                  <dd className="whitespace-pre-line text-[15px] font-medium">{value}</dd>
                </div>
              ))}
            </dl>
          </div>
        </section>

        <section id="faq" className="flex flex-col items-center gap-4 border-t border-line px-8 pb-10 pt-20 text-center max-sm:px-4">
          <Pill tag="02">FAQ</Pill>
          <h2 className="text-[clamp(34px,4vw,52px)] font-medium leading-[1.05] tracking-[-0.04em]">Before you call</h2>
        </section>
        <section className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,340px),1fr))] gap-6 px-8 pb-[72px] pt-4 max-sm:px-4">
          <div className="flex min-h-[340px] flex-col items-center justify-center gap-[18px] rounded-3xl bg-surface-muted p-7 text-center">
            <Orb size={120} mode="hero" />
            <div className="flex flex-col gap-1">
              <span className="text-xl font-medium tracking-[-0.02em]">Mia&apos;s ready when you are</span>
              <span className="text-[13.5px] text-ink-muted">Headphones recommended. Allow your microphone when asked.</span>
            </div>
            <button type="button" onClick={call} disabled={offline} className={`${primaryButton} h-12 px-[26px] text-[13px]`}>
              START A CALL
            </button>
          </div>
          <div className="flex flex-col gap-2.5">
            {FAQS.map((faq, i) => {
              const open = openFaq === i;
              return (
                <div key={faq.q} className="rounded-2xl bg-surface-muted transition-colors hover:bg-[#efefec]">
                  <button
                    type="button"
                    onClick={() => setOpenFaq(open ? null : i)}
                    aria-expanded={open}
                    className="flex w-full items-center gap-3.5 px-5 py-[18px] text-left"
                  >
                    <span className="font-mono text-xs font-medium text-ink-ghost">{String(i + 1).padStart(2, "0")}</span>
                    <span className="flex-1 text-[15px] font-medium">{faq.q}</span>
                    <span className="w-[18px] text-center text-lg text-ink-muted" aria-hidden>
                      {open ? "−" : "+"}
                    </span>
                  </button>
                  {open && (
                    <p className="-mt-2 pb-[18px] pl-[52px] pr-5 text-sm leading-[1.55] text-ink-muted">{faq.a}</p>
                  )}
                </div>
              );
            })}
          </div>
        </section>

        <footer className="flex flex-wrap justify-between gap-4 border-t border-line px-8 py-[22px] text-[12.5px] text-ink-faint max-sm:px-4">
          <span>Bayview Family Clinic is fictional. Don&apos;t share real medical information.</span>
          <span>Demo data is deleted after 24 hours.</span>
        </footer>
      </div>
    </div>
  );
}

function Feature({
  title,
  body,
  bordered,
  children,
}: {
  title: string;
  body: string;
  bordered?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className={`flex flex-col gap-5 px-8 pb-8 pt-7 max-sm:px-4 ${bordered ? "border-l border-line max-[600px]:border-l-0 max-[600px]:border-t" : ""}`}>
      <div className="flex h-[170px] flex-col justify-center gap-1.5 rounded-[20px] bg-surface-muted p-[18px]">{children}</div>
      <div className="flex flex-col gap-1.5 text-left">
        <span className="text-lg font-medium tracking-[-0.02em]">{title}</span>
        <span className="text-sm leading-normal text-ink-muted">{body}</span>
      </div>
    </div>
  );
}
