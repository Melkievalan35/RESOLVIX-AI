import { useState } from "react";
import DashboardLayout from "../components/layout/DashboardLayout";

export default function Complaint() {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("refund");
  const [file, setFile] = useState(null);

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  async function submitComplaint(e) {
    e.preventDefault();

    setLoading(true);
    setError("");
    setResult(null);

    try {
      const token = localStorage.getItem("token");

      if (!token) {
        throw new Error("You are not logged in. Please login again.");
      }

      const formData = new FormData();

      formData.append("title", title);
      formData.append("description", description);
      formData.append("category", category);

      if (file) {
        formData.append("files", file);
      }

      const response = await fetch(
        "http://127.0.0.1:8000/complaints/submit",
        {
          method: "POST",
          headers: {
            Authorization: `Bearer ${token}`,
          },
          body: formData,
        }
      );

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data?.detail
            ? JSON.stringify(data.detail)
            : "Complaint submission failed"
        );
      }

      setResult(data);

    } catch (err) {
      console.error(err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <DashboardLayout>

      <div className="max-w-4xl">

        <h1 className="text-4xl font-bold mb-2">
          Submit Complaint
        </h1>

        <p className="text-slate-400 mb-8">
          Upload your complaint and evidence. Resolvix-AI will analyze it automatically.
        </p>

        {/* FORM */}

        <form
          onSubmit={submitComplaint}
          className="bg-slate-900 border border-slate-800 rounded-2xl p-8"
        >

          {/* TITLE */}

          <div className="mb-6">
            <label className="block text-slate-300 mb-2">
              Complaint Title
            </label>

            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Cracked phone screen"
              required
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-3 text-white outline-none"
            />
          </div>

          {/* DESCRIPTION */}

          <div className="mb-6">
            <label className="block text-slate-300 mb-2">
              Description
            </label>

            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="My phone arrived with a cracked screen and I need a refund."
              required
              rows={5}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-3 text-white outline-none"
            />
          </div>

          {/* CATEGORY */}

          <div className="mb-6">
            <label className="block text-slate-300 mb-2">
              Category
            </label>

            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg px-4 py-3 text-white"
            >
              <option value="refund">Refund</option>
              <option value="damaged_product">
                Damaged Product
              </option>
              <option value="replacement">
                Replacement
              </option>
              <option value="delivery">
                Delivery
              </option>
              <option value="other">
                Other
              </option>
            </select>
          </div>

          {/* FILE */}

          <div className="mb-8">
            <label className="block text-slate-300 mb-2">
              Evidence / Product Image
            </label>

            <input
              type="file"
              accept="image/*,.pdf"
              onChange={(e) => {
                setFile(e.target.files[0]);
              }}
              className="w-full bg-slate-800 border border-slate-700 rounded-lg p-3 text-slate-300"
            />

            {file && (
              <p className="text-green-400 mt-3">
                ✓ Selected: {file.name}
              </p>
            )}
          </div>

          {/* SUBMIT */}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-slate-700 text-white font-semibold rounded-lg py-3 transition"
          >
            {loading
              ? "AI is analyzing your complaint..."
              : "Submit Complaint"}
          </button>

        </form>

        {/* ERROR */}

        {error && (
          <div className="mt-6 bg-red-950 border border-red-700 rounded-xl p-5">
            <h2 className="text-red-400 font-bold mb-2">
              ❌ Submission Error
            </h2>

            <pre className="text-red-300 text-sm whitespace-pre-wrap">
              {error}
            </pre>
          </div>
        )}

        {/* SUCCESS */}

        {result && (
          <div className="mt-6 bg-slate-900 border border-green-700 rounded-2xl p-6">

            <h2 className="text-2xl font-bold text-green-400 mb-5">
              ✅ AI Analysis Complete
            </h2>

            <div className="grid grid-cols-2 gap-4 mb-6">

              <div className="bg-slate-800 rounded-lg p-4">
                <p className="text-slate-400 text-sm">
                  Complaint ID
                </p>

                <p className="text-white font-semibold mt-1">
                  {result.complaint_id}
                </p>
              </div>

              <div className="bg-slate-800 rounded-lg p-4">
                <p className="text-slate-400 text-sm">
                  Category
                </p>

                <p className="text-white font-semibold mt-1">
                  {result.category}
                </p>
              </div>

              <div className="bg-slate-800 rounded-lg p-4">
                <p className="text-slate-400 text-sm">
                  Workflow
                </p>

                <p className="text-blue-400 font-semibold mt-1">
                  {result.workflow}
                </p>
              </div>

              <div className="bg-slate-800 rounded-lg p-4">
                <p className="text-slate-400 text-sm">
                  Fraud Score
                </p>

                <p className="text-green-400 font-semibold mt-1">
                  {result.fraud_score}
                </p>
              </div>

            </div>

            <div className="bg-slate-800 rounded-xl p-5">

              <h3 className="text-lg font-bold text-white mb-3">
                AI Resolution
              </h3>

              <pre className="text-slate-300 text-sm whitespace-pre-wrap">
                {JSON.stringify(
                  result.resolution,
                  null,
                  2
                )}
              </pre>

            </div>

            <div className="bg-slate-800 rounded-xl p-5 mt-4">

              <h3 className="text-lg font-bold text-white mb-3">
                Agent Processing
              </h3>

              <pre className="text-slate-300 text-xs whitespace-pre-wrap overflow-auto max-h-96">
                {JSON.stringify(
                  result.trace,
                  null,
                  2
                )}
              </pre>

            </div>

          </div>
        )}

      </div>

    </DashboardLayout>
  );
}