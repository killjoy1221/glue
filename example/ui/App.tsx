import { useState, useEffect } from "react";

const API_BASE_URL = "http://api.localhost:8000";

export default function App() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error>();
  const [data, setData] = useState<{ clicks: number }>();

  async function executeClick(path: string, options?: RequestInit) {
    setLoading(true);
    fetch(`${API_BASE_URL}${path}`, options)
      .then(async (resp) => {
        if (resp.ok) {
          return await resp.json();
        }

        throw new Error(await resp.text());
      })
      .then(setData)
      .catch(setError)
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    executeClick("/clicks");
  }, []);

  const onClick = () => {
    executeClick("/click", { method: "POST" });
  };

  const onReset = () => {
    executeClick("/reset", { method: "POST" });
  };

  return (
    <div>
      {error && <p>Error: {error.toString()}</p>}

      <button onClick={onClick} disabled={loading}>
        {!data?.clicks ? "Click Me!" : `Clicks: ${data?.clicks ?? 0}`}
      </button>
      <button onClick={onReset} disabled={!data?.clicks}>
        Reset
      </button>
    </div>
  );
}
