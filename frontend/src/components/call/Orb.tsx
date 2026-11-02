export function Orb({ speaking }: { speaking: boolean }) {
  return (
    <div className="relative size-14 shrink-0" aria-label={speaking ? "Mia is speaking" : "Mia is listening"}>
      {speaking && <span className="animate-orb absolute inset-0 rounded-full bg-brand" />}
      <span
        className={`absolute inset-1 rounded-full bg-gradient-to-br from-teal-300 to-brand shadow-inner transition-transform duration-200 ${
          speaking ? "scale-105" : "scale-95"
        }`}
      />
    </div>
  );
}
