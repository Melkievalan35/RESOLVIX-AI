import DashboardLayout from "../components/layout/DashboardLayout";

export default function Dashboard() {
  return (
    <DashboardLayout>
      <div className="max-w-7xl mx-auto">

        {/* Header */}
        <div className="mb-8">
          <h1 className="text-4xl font-bold text-white">
            Dashboard
          </h1>

          <p className="text-slate-400 mt-2">
            AI Powered Complaint Resolution Platform
          </p>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-4 gap-6">

          {/* Open Complaints */}
          <div className="bg-slate-900 rounded-2xl p-6 border border-slate-800">
            <p className="text-slate-400">
              Open Complaints
            </p>

            <h2 className="text-4xl font-bold mt-3 text-white">
              2
            </h2>

            <p className="text-yellow-400 text-sm mt-2">
              Requires attention
            </p>
          </div>

          {/* Resolved Today */}
          <div className="bg-slate-900 rounded-2xl p-6 border border-slate-800">
            <p className="text-slate-400">
              Resolved Today
            </p>

            <h2 className="text-4xl font-bold mt-3 text-green-400">
              1
            </h2>

            <p className="text-slate-500 text-sm mt-2">
              AI resolved
            </p>
          </div>

          {/* SLA Breaches */}
          <div className="bg-slate-900 rounded-2xl p-6 border border-slate-800">
            <p className="text-slate-400">
              SLA Breaches
            </p>

            <h2 className="text-4xl font-bold mt-3 text-red-400">
              0
            </h2>

            <p className="text-green-400 text-sm mt-2">
              No breaches
            </p>
          </div>

          {/* Auto Resolution */}
          <div className="bg-slate-900 rounded-2xl p-6 border border-slate-800">
            <p className="text-slate-400">
              Auto Resolution
            </p>

            <h2 className="text-4xl font-bold mt-3 text-blue-400">
              33%
            </h2>

            <p className="text-slate-500 text-sm mt-2">
              AI automation rate
            </p>
          </div>

        </div>

        {/* AI Overview */}
        <div className="grid grid-cols-3 gap-6 mt-8">

          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
            <p className="text-slate-400">
              AI Complaints Analyzed
            </p>

            <h2 className="text-3xl font-bold text-white mt-3">
              3
            </h2>

            <p className="text-blue-400 text-sm mt-2">
              Multi-agent processing
            </p>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
            <p className="text-slate-400">
              Fraud Risk
            </p>

            <h2 className="text-3xl font-bold text-green-400 mt-3">
              Low
            </h2>

            <p className="text-slate-500 text-sm mt-2">
              Average score: 0.10
            </p>
          </div>

          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
            <p className="text-slate-400">
              AI Vision Detection
            </p>

            <h2 className="text-3xl font-bold text-green-400 mt-3">
              Active
            </h2>

            <p className="text-slate-500 text-sm mt-2">
              Damage detection enabled
            </p>
          </div>

        </div>

        {/* Recent Activity */}
        <div className="mt-8 bg-slate-900 border border-slate-800 rounded-2xl p-6">

          <h2 className="text-xl font-semibold text-white mb-5">
            Recent AI Activity
          </h2>

          <div className="space-y-4">

            <Activity
              title="Cracked Phone Screen - Refund Request"
              category="Damaged Product"
              status="Escalated"
              time="Today"
            />

            <Activity
              title="Product Damage Complaint"
              category="Damaged Product"
              status="Escalated"
              time="Today"
            />

            <Activity
              title="Phone Refund Request"
              category="Refund"
              status="Resolved"
              time="Yesterday"
            />

          </div>

        </div>

      </div>
    </DashboardLayout>
  );
}

function Activity({ title, category, status, time }) {
  return (
    <div className="flex justify-between items-center border-b border-slate-800 pb-4">

      <div>
        <p className="text-white font-medium">
          {title}
        </p>

        <p className="text-slate-500 text-sm mt-1">
          {category} • {time}
        </p>
      </div>

      <span
        className={`px-3 py-1 rounded-full text-xs ${
          status === "Resolved"
            ? "bg-green-500/10 text-green-400"
            : "bg-yellow-500/10 text-yellow-400"
        }`}
      >
        {status}
      </span>

    </div>
  );
}