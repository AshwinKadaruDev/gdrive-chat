import { useState, useRef, useEffect } from "react";
import { ChevronDown } from "lucide-react";

const MODELS = [
  { id: "gpt-5.2", label: "GPT 5.2" },
  { id: "claude-opus-4-5-20251101", label: "Opus 4.5" },
];

interface ModelSelectorProps {
  model: string;
  onChange: (model: string) => void;
}

export default function ModelSelector({ model, onChange }: ModelSelectorProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const selected = MODELS.find((m) => m.id === model) ?? MODELS[0];

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1 rounded-md px-2 py-1 text-[12px] text-surface-100/60 transition-colors hover:text-surface-100"
      >
        {selected.label}
        <ChevronDown className="h-3 w-3" />
      </button>
      {open && (
        <div className="absolute bottom-full left-0 mb-1 min-w-[140px] rounded-lg border border-[var(--border-subtle)] bg-surface-800 py-1 shadow-xl">
          {MODELS.map((m) => (
            <button
              key={m.id}
              onClick={() => {
                onChange(m.id);
                setOpen(false);
              }}
              className={`w-full px-3 py-1.5 text-left text-[12px] transition-colors hover:bg-[var(--hover-overlay)] ${
                m.id === model ? "text-brand-500" : "text-fg-primary"
              }`}
            >
              {m.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
