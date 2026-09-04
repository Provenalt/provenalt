export function StatCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="panel px-4 py-4">
      <div className="eyebrow">{label}</div>
      <div className="mono mt-2 text-[1.75rem] font-500 leading-none text-fg">{value}</div>
      {hint ? <div className="mt-1.5 text-xs text-fg-faint">{hint}</div> : null}
    </div>
  );
}
