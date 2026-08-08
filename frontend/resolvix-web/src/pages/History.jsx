import { useEffect, useState } from "react";
import DashboardLayout from "../components/layout/DashboardLayout";
import api from "../services/api";

export default function History() {
  const [complaints, setComplaints] = useState([]);
  const [filter, setFilter] = useState("All");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadComplaints() {
    try {
      setLoading(true);
      setError("");

      const response = await api.get("/complaints/");

      console.log("History response:", response.data);

      const data = Array.isArray(response.data)
        ? response.data
        : response.data.items ||
          response.data.complaints ||
          [];

      setComplaints(data);
    } catch (err) {
      console.error("HISTORY ERROR:", err);
      console.error("STATUS:", err.response?.status);
      console.error("DATA:", err.response?.data);
      console.error("URL:", err.config?.url);

      setError(
        `Unable to load complaint history (${
          err.response?.status || "Network Error"
        })`
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadComplaints();
  }, []);

  const filtered = complaints.filter((complaint) => {
    if (filter === "All") {
      return true;
    }

    const status = String(
      complaint.status || ""
    ).toLowerCase();

    return status === filter.toLowerCase();
  });

  function formatDate(date) {
    if (!date) {
      return "-";
    }

    try {
      return new Date(date).toLocaleDateString(
        "en-IN",
        {
          day: "2-digit",
          month: "short",
          year: "numeric",
        }
      );
    } catch {
      return "-";
    }
  }

  function formatText(value) {
    if (!value) {
      return "-";
    }

    return String(value)
      .replaceAll("_", " ")
      .replace(/\b\w/g, (char) =>
        char.toUpperCase()
      );
  }

  function getResolution(complaint) {
    if (
      typeof complaint.resolution === "string"
    ) {
      return complaint.resolution;
    }

    if (
      typeof complaint.ai_resolution === "string"
    ) {
      return complaint.ai_resolution;
    }

    if (
      complaint.resolution_data?.decision
    ) {
      return complaint.resolution_data.decision;
    }

    const status = String(
      complaint.status || ""
    ).toUpperCase();

    if (status === "RESOLVED") {
      return "Resolved";
    }

    if (status === "ESCALATED") {
      return "Manual Review";
    }

    return "Processing";
  }

  return (
    <DashboardLayout>
      <div className="mb-8">
        <div className="flex justify-between items-center">
          <div>
            <h1 className="text-4xl font-bold text-white">
              Complaint History
            </h1>

            <p className="text-slate-400 mt-2">
              View your previous complaints and AI decisions.
            </p>
          </div>

          <select
            value={filter}
            onChange={(e) =>
              setFilter(e.target.value)
            }
            className="bg-slate-900 border border-slate-700 text-white rounded-xl px-4 py-3"
          >
            <option value="All">All</option>
            <option value="Resolved">
              Resolved
            </option>
            <option value="Escalated">
              Escalated
            </option>
            <option value="Submitted">
              Submitted
            </option>
            <option value="Open">Open</option>
          </select>
        </div>
      </div>

      {loading && (
        <div className="text-slate-400">
          Loading complaint history...
        </div>
      )}

      {error && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-400 rounded-xl p-4 mb-6">
          {error}
        </div>
      )}

      {!loading &&
        !error &&
        filtered.length === 0 && (
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 text-center">
            <p className="text-slate-400">
              No complaints found.
            </p>
          </div>
        )}

      <div className="space-y-4">
        {filtered.map((complaint) => {
          const status = String(
            complaint.status || ""
          ).toUpperCase();

          const isResolved =
            status === "RESOLVED";

          return (
            <div
              key={complaint.id}
              className="bg-slate-900 border border-slate-800 rounded-2xl p-6 hover:border-slate-600 transition"
            >
              <div className="flex justify-between items-start">
                <div>
                  <div className="flex items-center gap-3">
                    <h2 className="text-xl font-semibold text-white">
                      {complaint.title ||
                        "Untitled Complaint"}
                    </h2>

                    <span
                      className={`px-3 py-1 rounded-full text-xs font-medium ${
                        isResolved
                          ? "bg-green-500/10 text-green-400"
                          : "bg-yellow-500/10 text-yellow-400"
                      }`}
                    >
                      {formatText(
                        complaint.status
                      )}
                    </span>
                  </div>

                  <p className="text-slate-500 text-sm mt-2">
                    ID:{" "}
                    {String(
                      complaint.id || ""
                    ).slice(0, 8)}
                  </p>
                </div>

                <span className="text-slate-500 text-sm">
                  {formatDate(
                    complaint.created_at
                  )}
                </span>
              </div>

              <div className="grid grid-cols-3 gap-4 mt-6">
                <div className="bg-slate-950 rounded-xl p-4">
                  <p className="text-slate-500 text-sm">
                    Category
                  </p>

                  <p className="text-white font-medium mt-1">
                    {formatText(
                      complaint.category
                    )}
                  </p>
                </div>

                <div className="bg-slate-950 rounded-xl p-4">
                  <p className="text-slate-500 text-sm">
                    Fraud Score
                  </p>

                  <p className="text-green-400 font-semibold mt-1">
                    {complaint.fraud_score !=
                    null
                      ? Number(
                          complaint.fraud_score
                        ).toFixed(2)
                      : "0.00"}
                  </p>
                </div>

                <div className="bg-slate-950 rounded-xl p-4">
                  <p className="text-slate-500 text-sm">
                    AI Resolution
                  </p>

                  <p className="text-white font-medium mt-1">
                    {formatText(
                      getResolution(
                        complaint
                      )
                    )}
                  </p>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </DashboardLayout>
  );
}