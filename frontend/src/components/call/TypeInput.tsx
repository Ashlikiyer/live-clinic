"use client";

import { useState } from "react";

export const MAX_TYPED_CHARS = 300;

/** "Type instead": typed messages take the same path as speech, and Mia still answers aloud. */
export function TypeInput({
  disabled,
  onSend,
  onTyping,
}: {
  disabled: boolean;
  onSend: ((text: string) => void) | null;
  onTyping?: () => void;
}) {
  const [text, setText] = useState("");
  const canSend = !disabled && onSend !== null && text.trim().length > 0;

  return (
    <form
      className="flex gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (!canSend) return;
        onSend(text);
        setText("");
      }}
    >
      <label htmlFor="type-instead" className="sr-only">
        Type instead
      </label>
      <input
        id="type-instead"
        value={text}
        onChange={(e) => {
          setText(e.target.value.slice(0, MAX_TYPED_CHARS));
          onTyping?.();
        }}
        disabled={disabled}
        maxLength={MAX_TYPED_CHARS}
        autoComplete="off"
        placeholder={onSend ? "Type instead…" : "Typing is off in the demo"}
        className="h-11 min-w-0 flex-1 rounded-full border border-line bg-bg px-4 text-sm outline-none focus:border-ink disabled:opacity-50"
      />
      <button
        type="submit"
        disabled={!canSend}
        aria-label="Send"
        className="grid size-11 flex-none place-items-center rounded-full bg-ink text-base text-white transition-opacity disabled:opacity-30"
      >
        ↑
      </button>
    </form>
  );
}
