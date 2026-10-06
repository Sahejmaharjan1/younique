"use client";

import { useEffect, useState } from "react";
import { ErrorNotice } from "@/features/errors/ErrorNotice";
import { ApiError, api } from "@/lib/api";

type Artifact = {
  id: string;
  name: string;
  status: string;
  detected_mime: string | null;
};

export default function ArtifactsPage() {
  const [rows, setRows] = useState<Artifact[]>([]);
  const [notice, setNotice] = useState("");

  async function load() {
    const body = await api<{ data: Artifact[] }>("/api/v1/artifacts");
    setRows(body.data);
  }

  useEffect(() => {
    void load();
  }, []);

  async function upload(file: File) {
    const reserved = await api<{
      artifact_id: string;
      upload_url: string;
      upload_token: string;
      gcs_upload_url: string;
    }>("/api/v1/artifacts", {
      method: "POST",
      body: JSON.stringify({
        name: file.name,
        declared_mime: file.type || "text/plain",
        byte_size: file.size,
      }),
    });
    const target = reserved.upload_url.startsWith("http")
      ? reserved.upload_url
      : `/api${reserved.upload_url}`;
    const csrf = document.cookie
      .split("; ")
      .find((part) => part.startsWith("csrf="))
      ?.split("=")[1];
    const response = await fetch(target, {
      method: "PUT",
      credentials: "include",
      headers: {
        "x-upload-token": reserved.upload_token,
        "x-csrf-token": csrf ? decodeURIComponent(csrf) : "",
        "content-type": "application/octet-stream",
      },
      body: file,
    });
    if (!response.ok) {
      setNotice("Upload failed");
      return;
    }
    await load();
  }

  return (
    <main>
      <h1>Artifacts</h1>
      <p>
        Uploads stay blocked until a scan marks them clean. An infected file is
        never downloadable.
      </p>
      <input
        aria-label="Upload file"
        type="file"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void upload(file);
        }}
      />
      {rows.map((row) => (
        <article className="card" key={row.id}>
          <p>
            {row.name} · {row.status}
            {row.status === "infected" ? " · infected" : ""}
          </p>
          <button
            type="button"
            onClick={() => {
              void api(`/api/v1/artifacts/${row.id}/download`).catch(
                (caught: unknown) => {
                  if (caught instanceof ApiError) setNotice(caught.code);
                },
              );
            }}
          >
            Download
          </button>
        </article>
      ))}
      {notice === "artifact_not_clean" ? (
        <ErrorNotice
          code="artifact_not_clean"
          detail="Download is blocked while the file is infected."
        />
      ) : null}
    </main>
  );
}
