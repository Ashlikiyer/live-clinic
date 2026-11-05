import { create } from "zustand";

import { DOCTORS, type Doctor } from "@/lib/clinic";
import type { ServerEvent } from "@/realtime/events";
import type { SocketStatus } from "@/realtime/socket";

import {
  addLocalLine,
  applyServerEvent,
  beginTurn,
  mergeCalendarDay,
  type CalendarDay,
  initialCallData,
  markInterrupted,
  type BusySlot,
  type CallData,
} from "./reducer";

export type CallKind = "live" | "demo";
export type MicState = "off" | "starting" | "listening" | "denied" | "unavailable";
export type VoiceMode = "orpheus" | "kokoro" | "lite";

/** Live audio/UI state that changes often and is never derived from server events. */
interface CallUi {
  kind: CallKind | null;
  startedAt: number | null;
  endedAt: number | null;
  agentSpeaking: boolean;
  userSpeaking: boolean;
  micLevel: number;
  muted: boolean;
  mic: MicState;
  voiceMode: VoiceMode;
  connection: SocketStatus | "idle";
  /** A message for the caller, e.g. "Busy right now, try again in a minute." */
  notice: string | null;
  doctors: Doctor[];
}

interface CallActions {
  startCall: (now: number, kind: CallKind) => void;
  applyEvent: (event: ServerEvent) => void;
  interrupt: (turnId: number, playedText: string) => void;
  beginTurn: (turnId: number) => void;
  setBusyDay: (date: string, slots: BusySlot[]) => void;
  loadCalendarDay: (day: CalendarDay) => void;
  setDoctors: (doctors: Doctor[]) => void;
  addLocalLine: (text: string) => void;
  selectDate: (date: string) => void;
  markSeen: (panel: "calendar" | "form") => void;
  setAgentSpeaking: (speaking: boolean) => void;
  setUserSpeaking: (speaking: boolean) => void;
  setMicLevel: (level: number) => void;
  setMuted: (muted: boolean) => void;
  setMic: (mic: MicState) => void;
  setVoiceMode: (mode: VoiceMode) => void;
  setConnection: (connection: CallUi["connection"]) => void;
  setNotice: (notice: string | null) => void;
  reset: () => void;
}

export type CallStore = CallData & CallUi & CallActions;

const initialUi: CallUi = {
  kind: null,
  startedAt: null,
  endedAt: null,
  agentSpeaking: false,
  userSpeaking: false,
  micLevel: 0,
  muted: false,
  mic: "off",
  voiceMode: "kokoro",
  connection: "idle",
  notice: null,
  doctors: DOCTORS,
};

export const useCallStore = create<CallStore>()((set) => ({
  ...initialCallData,
  ...initialUi,

  startCall: (now, kind) =>
    set({ ...initialCallData, ...initialUi, status: "connecting", startedAt: now, kind }),

  applyEvent: (event) =>
    set((state) => {
      const next = applyServerEvent(state, event);
      if (next.status === "ended" && state.status !== "ended") {
        return { ...next, endedAt: event.ts, micLevel: 0, userSpeaking: false };
      }
      return next;
    }),

  interrupt: (turnId, playedText) =>
    set((state) => ({ ...markInterrupted(state, turnId, playedText), agentSpeaking: false })),

  beginTurn: (turnId) => set((state) => beginTurn(state, turnId)),

  setBusyDay: (date, slots) => set((state) => ({ busy: { ...state.busy, [date]: slots } })),

  loadCalendarDay: (day) => set((state) => mergeCalendarDay(state, day)),

  setDoctors: (doctors) => set({ doctors }),

  addLocalLine: (text) => set((state) => addLocalLine(state, text, Date.now())),

  selectDate: (date) => set({ calendarDate: date }),

  markSeen: (panel) => set((state) => ({ unseen: { ...state.unseen, [panel]: false } })),

  setAgentSpeaking: (agentSpeaking) => set({ agentSpeaking }),

  setUserSpeaking: (userSpeaking) => set({ userSpeaking }),

  setMicLevel: (micLevel) => set({ micLevel }),

  setMuted: (muted) => set({ muted, micLevel: 0 }),

  setMic: (mic) => set({ mic }),

  setVoiceMode: (voiceMode) => set({ voiceMode }),

  setConnection: (connection) => set({ connection }),

  setNotice: (notice) => set({ notice }),

  reset: () => set({ ...initialCallData, ...initialUi }),
}));
