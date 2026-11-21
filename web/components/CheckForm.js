"use client";
// Address field + video drop zone + button. Both pages use it; the demo page passes
// its extra settings (key frames, detector, simulated levels) as children.
import { useRef, useState } from "react";

export default function CheckForm({ onSubmit, busy, buttonText, children }) {
  const [address, setAddress] = useState("Route Cantonale, Lausanne");
  const [file, setFile] = useState(null);
  const [dragging, setDragging] = useState(false);
  const input = useRef(null);

  function onDrop(event) {
    event.preventDefault();
    setDragging(false);
    if (event.dataTransfer.files[0]) setFile(event.dataTransfer.files[0]);
  }

  function submit(event) {
    event.preventDefault();
    if (address.trim() && file && !busy) onSubmit(address.trim(), file);
  }

  return (
    <form className="check-form" onSubmit={submit}>
      <label className="field">
        <span>Site address</span>
        <input value={address} onChange={(e) => setAddress(e.target.value)}
               placeholder="Street and town in Switzerland" required />
      </label>

      <div className={`drop ${dragging ? "drop--over" : ""}`}
           onClick={() => input.current.click()}
           onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
           onDragLeave={() => setDragging(false)}
           onDrop={onDrop} role="button" tabIndex={0}
           onKeyDown={(e) => e.key === "Enter" && input.current.click()}>
        {file
          ? <span><b>{file.name}</b> · {(file.size / 1e6).toFixed(0)} MB</span>
          : <span>Drop your walk-around video here, or <u>choose a file</u></span>}
        <small>About 60 seconds, straight from the phone (iPhone .MOV is fine)</small>
        {/* accept also lists .mov: some browsers do not count iPhone HEVC files as video/* */}
        <input ref={input} type="file" accept="video/*,.mov,.mp4,.m4v" hidden
               onChange={(e) => setFile(e.target.files[0] || null)} />
      </div>

      {children}

      <button className="button" type="submit" disabled={!file || !address.trim() || busy}>
        {buttonText}
      </button>
    </form>
  );
}
