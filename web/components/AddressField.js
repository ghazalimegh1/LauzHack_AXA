"use client";
// Address input with suggestions from the official Swiss address search (via our server).
// Typing still works without suggestions: they only save the customer from typos.
import { useEffect, useRef, useState } from "react";
import { suggestAddresses } from "../lib/api";

const WAIT_MS = 300;   // ask only after a short pause in typing, not on every key

export default function AddressField({ value, onChange }) {
  const [options, setOptions] = useState([]);
  const [open, setOpen] = useState(false);
  // Search only for what the customer typed: not for the prefilled address on page load,
  // and not again for a suggestion they just picked.
  const typed = useRef(false);

  useEffect(() => {
    if (!typed.current) return undefined;
    typed.current = false;
    let alive = true;
    const t = setTimeout(() => suggestAddresses(value).then((s) => {
      if (alive) { setOptions(s); setOpen(s.length > 0); }
    }), WAIT_MS);
    return () => { alive = false; clearTimeout(t); };
  }, [value]);

  function choose(label) {
    onChange(label);
    setOpen(false);
  }

  function type(e) {
    typed.current = true;
    onChange(e.target.value);
  }

  return (
    <label className="field address">
      <span>Address of your business</span>
      <input value={value} onChange={type} autoComplete="off"
             placeholder="Street, number and town" required
             onBlur={() => setTimeout(() => setOpen(false), 150)}
             onFocus={() => options.length && setOpen(true)} />
      {open && (
        <ul className="suggestions" role="listbox">
          {options.map((o) => (
            <li key={o} role="option" aria-selected="false" onMouseDown={() => choose(o)}>{o}</li>
          ))}
        </ul>
      )}
    </label>
  );
}
