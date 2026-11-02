"use client";

import { useState } from "react";

export const MAX_TYPED_CHARS = 300;

/** "Type instead" input. Phase 0 shows it only; Phase 1 sends `text.message` over the socket. */
export function TypeInput({ disabled }: { disabled: boolean }) {
  const [text, setText] = useState("");

  return (
    <form
      className="flex gap-2"
      onSubmit={(e) => {
        e.preventDefault();
        setText("");
      }}
    >
      <label htmlFor="type-instead" className="sr-only">
        Type instead
      </label>
      <input
        id="type-instead"
        value={text}
        onChange={(e) => setText(e.target.value.slice(0, MAX_TYPED_CHARS))}
        disabled={disabled}
        placeholder="Type instead (available in Phase 1)"
        className="min-w-0 flex-1 rounded-full border border-line bg-surface px-4 py-2 text-sm outline-none focus:border-brand disabled:opacity-50"
      />
      <button
        type="submit"
        disabled
        className="rounded-full bg-surface-muted px-4 py-2 text-sm font-medium text-ink-muted"
      >
        Send
      </button>
    </form>
  );
}
