import { useMemo, useRef, useState } from "react";

function getApiBase() {
  const explicit = import.meta.env.VITE_API_BASE_URL;
  if (explicit && explicit.trim().length > 0) {
    return explicit;
  }
  const port = import.meta.env.VITE_API_PORT || "8000";
  return `${window.location.protocol}//${window.location.hostname}:${port}`;
}

const API_BASE = getApiBase();

function wsUrlForTask(taskId) {
  const url = new URL(API_BASE);
  const scheme = url.protocol === "https:" ? "wss:" : "ws:";
  return `${scheme}//${url.host}/ws/tasks/${taskId}`;
}

export default function App() {
  const [userId, setUserId] = useState("demo-user-1");
  const [file, setFile] = useState(null);
  const [task, setTask] = useState(null);
  const [error, setError] = useState("");
  const wsRef = useRef(null);

  const progress = useMemo(() => task?.progress ?? 0, [task]);

  async function upload() {
    if (!file) {
      setError("Select a file first.");
      return;
    }
    setError("");

    const formData = new FormData();
    formData.append("file", file);
    formData.append("user_id", userId);

    const response = await fetch(`${API_BASE}/media/upload`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      setError(body?.detail || "Upload failed");
      return;
    }

    const data = await response.json();
    connectWs(data.task_id);
  }

  function connectWs(taskId) {
    wsRef.current?.close();
    const ws = new WebSocket(wsUrlForTask(taskId));
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      setTask(payload);
      if (payload.status === "completed" || payload.status === "failed") {
        ws.close();
      }
    };

    ws.onerror = () => setError("WebSocket connection error");
  }

  return (
    <div className="page">
      <div className="panel">
        <h1>Celery Media Processing Platform</h1>
        <p className="subtitle">
          Upload media and watch a real-time Celery pipeline progress.
        </p>

        <label>
          User ID
          <input value={userId} onChange={(e) => setUserId(e.target.value)} />
        </label>

        <label>
          File
          <input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} />
        </label>

        <button onClick={upload}>Upload & Process</button>

        {error ? <p className="error">{error}</p> : null}

        {task ? (
          <div className="status">
            <p>
              <strong>Status:</strong> {task.status}
            </p>
            <p>
              <strong>Progress:</strong> {progress}%
            </p>
            <div className="bar">
              <div className="fill" style={{ width: `${progress}%` }} />
            </div>

            {task.outputs?.thumbnail ? (
              <div className="result">
                <p>
                  <strong>Thumbnail:</strong>{" "}
                  <a href={task.outputs.thumbnail} target="_blank" rel="noreferrer">
                    open
                  </a>
                </p>
                <ul>
                  {(task.outputs.variants || []).map((item) => (
                    <li key={item.label}>
                      {item.label}:{" "}
                      <a href={item.url} target="_blank" rel="noreferrer">
                        open
                      </a>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : null}
      </div>
    </div>
  );
}
