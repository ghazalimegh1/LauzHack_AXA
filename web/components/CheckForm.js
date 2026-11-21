"use client";

import { useEffect, useRef, useState } from "react";
import { suggest } from "../lib/api";

function AddressField({ value, onChange }) {
  const [items, setItems] = useState([]);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const typed = useRef(false);

  useEffect(() => {
    if (!typed.current || value.trim().length < 3) {
      setItems([]);
      return undefined;
    }
    let alive = true;
    const timer = setTimeout(async () => {
      try {
        const found = await suggest(value);
        if (alive) {
          setItems(found);
          setOpen(found.length > 0);
          setActive(-1);
        }
      } catch {
        if (alive) setItems([]);
      }
    }, 250);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [value]);

  function choose(text) {
    typed.current = false;
    onChange(text);
    setOpen(false);
  }

  function onKey(e) {
    if (!open || !items.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => (a + 1) % items.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (a <= 0 ? items.length - 1 : a - 1));
    } else if (e.key === "Enter" && active >= 0) {
      e.preventDefault();
      choose(items[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div className="field">
      <label htmlFor="address">Address of your site</label>
      <input
        id="address"
        className="input"
        type="text"
        autoComplete="off"
        placeholder="e.g. Route Cantonale 11, 1015 Lausanne"
        value={value}
        role="combobox"
        aria-expanded={open}
        aria-controls="address-list"
        aria-autocomplete="list"
        aria-activedescendant={active >= 0 ? `address-${active}` : undefined}
        onChange={(e) => {
          typed.current = true;
          onChange(e.target.value);
        }}
        onKeyDown={onKey}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        required
      />
      {open && items.length > 0 && (
        <ul className="suggestions" id="address-list" role="listbox">
          {items.map((item, i) => (
            <li
              key={item}
              id={`address-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => {
                e.preventDefault();
                choose(item);
              }}
            >
              {item}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function VideoDrop({ file, onFile }) {
  const [over, setOver] = useState(false);
  const [preview, setPreview] = useState(null);

  useEffect(() => {
    if (!file) {
      setPreview(null);
      return undefined;
    }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function take(list) {
    const f = list && list[0];
    if (f) onFile(f);
  }

  const mb = file ? (file.size / 1e6).toFixed(file.size > 1e8 ? 0 : 1) : 0;
  return (
    <div className="field">
      <span className="label-text" id="video-label">Walk-around video</span>
      <label
        className={`drop${over ? " over" : ""}${file ? " has-file" : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault();
          setOver(false);
          take(e.dataTransfer.files);
        }}
      >
        <input
          type="file"
          accept="video/*,.mov,.mp4,.m4v"
          className="visually-hidden"
          aria-labelledby="video-label"
          onChange={(e) => take(e.target.files)}
        />
        {file ? (
          <>
            {preview && <video src={preview} muted playsInline preload="metadata" aria-hidden="true" />}
            <span>
              <strong>{file.name}</strong>
              <br />
              <small>{mb} MB · click or drop to choose another video</small>
            </span>
          </>
        ) : (
          <span>
            <strong>Drop your video here</strong>
            <br />
            <small>or click to choose a file · a slow 30–60 second walk around the site works best</small>
          </span>
        )}
      </label>
    </div>
  );
}

export default function CheckForm({ onSubmit, error, children, submitLabel = "Check my site" }) {
  const [address, setAddress] = useState("");
  const [file, setFile] = useState(null);
  const [localError, setLocalError] = useState("");
  const [sending, setSending] = useState(false);

  async function submit(e) {
    e.preventDefault();
    if (address.trim().length < 3) return setLocalError("Please enter the address of your site.");
    if (!file) return setLocalError("Please add a video of your site.");
    setLocalError("");
    setSending(true);
    try {
      await onSubmit({ address: address.trim(), file });
    } finally {
      setSending(false);
    }
    return undefined;
  }

  const shown = localError || error;
  return (
    <form className="form" onSubmit={submit} noValidate>
      <AddressField value={address} onChange={setAddress} />
      <VideoDrop file={file} onFile={setFile} />
      {children}
      {shown && <p className="error" role="alert">{shown}</p>}
      <div className="actions">
        <button className="button" type="submit" disabled={sending}>
          {sending ? "Uploading…" : submitLabel}
        </button>
      </div>
    </form>
  );
}

export function Running({ stage }) {
  return (
    <div className="running" role="status" aria-live="polite">
      <div className="spinner" aria-hidden="true" />
      <div>
        <h2>{stage || "Starting the check"}</h2>
        <p className="quiet">This usually takes less than a minute. Please keep this page open.</p>
      </div>
    </div>
  );
}
