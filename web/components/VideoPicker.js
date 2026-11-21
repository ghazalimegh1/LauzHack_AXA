"use client";
// Record a video (phones open the camera) or choose one, then see it before sending.
import { useEffect, useRef, useState } from "react";

const ACCEPT = "video/*,.mov,.mp4,.m4v";   // .mov too: some browsers miss iPhone HEVC as video/*

export default function VideoPicker({ file, onFile }) {
  const [preview, setPreview] = useState("");
  const [touch, setTouch] = useState(false);
  const [dragging, setDragging] = useState(false);
  const record = useRef(null);
  const choose = useRef(null);

  // "Record" only makes sense where there is a camera to hand: phones and tablets.
  useEffect(() => { setTouch(window.matchMedia("(pointer: coarse)").matches); }, []);

  // A local preview of the chosen file (nothing is uploaded until "Check my site").
  useEffect(() => {
    if (!file) { setPreview(""); return undefined; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const pick = (e) => e.target.files[0] && onFile(e.target.files[0]);
  function onDrop(e) {
    e.preventDefault();
    setDragging(false);
    if (e.dataTransfer.files[0]) onFile(e.dataTransfer.files[0]);
  }

  return (
    <div className={`picker ${dragging ? "picker--over" : ""}`}
         onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
         onDragLeave={() => setDragging(false)} onDrop={onDrop}>
      {file ? (
        <div className="picked">
          {preview && <video src={preview} muted playsInline controls preload="metadata" />}
          <p className="picked-name"><b>{file.name}</b> · {(file.size / 1e6).toFixed(0)} MB</p>
        </div>
      ) : (
        <p className="picker-hint">{touch ? "Film a slow walk around your site." : "Drop a video here, or:"}</p>
      )}
      <div className="picker-buttons">
        {touch && (
          <button type="button" className="button" onClick={() => record.current.click()}>
            {file ? "Record again" : "Record a video"}
          </button>
        )}
        <button type="button" className={touch ? "button button--ghost" : "button"}
                onClick={() => choose.current.click()}>
          {file ? "Choose another" : "Choose a video"}
        </button>
      </div>
      <input ref={record} type="file" accept="video/*" capture="environment" hidden onChange={pick} />
      <input ref={choose} type="file" accept={ACCEPT} hidden onChange={pick} />
    </div>
  );
}
