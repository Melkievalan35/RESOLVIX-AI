import DashboardLayout from "../components/layout/DashboardLayout";

export default function Profile() {
  return (
    <DashboardLayout>
      <div className="max-w-6xl mx-auto">

        <div className="mb-8">
          <h1 className="text-4xl font-bold text-white">
            My Profile
          </h1>
          <p className="text-slate-400 mt-2">
            Your account and complaint activity.
          </p>
        </div>

        <div className="grid grid-cols-3 gap-6">

          {/* Profile Card */}
          <div className="col-span-1 bg-slate-900 border border-slate-800 rounded-2xl p-6">

            <div className="w-20 h-20 rounded-full bg-blue-600 flex items-center justify-center text-3xl font-bold text-white">
              M
            </div>

            <h2 className="text-2xl font-semibold text-white mt-5">
              Customer
            </h2>

            <p className="text-slate-400 mt-1">
              Resolvix-AI Customer
            </p>

            <div className="border-t border-slate-800 my-6" />

            <div className="space-y-4">

              <div>
                <p className="text-slate-500 text-sm">Customer ID</p>
                <p className="text-white mt-1">
                  cc90b054
                </p>
              </div>

              <div>
                <p className="text-slate-500 text-sm">Account Age</p>
                <p className="text-white mt-1">
                  365 days
                </p>
              </div>

              <div>
                <p className="text-slate-500 text-sm">Account Status</p>
                <span className="inline-block mt-1 px-3 py-1 rounded-full bg-green-500/10 text-green-400 text-sm">
                  Active
                </span>
              </div>

            </div>
          </div>

          {/* Statistics */}
          <div className="col-span-2 grid grid-cols-2 gap-6">

            <Stat
              title="Total Complaints"
              value="3"
              description="Submitted complaints"
            />

            <Stat
              title="Resolved"
              value="1"
              description="Successfully resolved"
              color="text-green-400"
            />

            <Stat
              title="Escalated"
              value="2"
              description="Human review required"
              color="text-yellow-400"
            />

            <Stat
              title="Fraud Score"
              value="0.10"
              description="Current risk score"
              color="text-blue-400"
            />

            <div className="col-span-2 bg-slate-900 border border-slate-800 rounded-2xl p-6">

              <h2 className="text-xl font-semibold text-white">
                AI Customer Insights
              </h2>

              <div className="mt-5 space-y-4">

                <Insight
                  label="Refund requests"
                  value="1"
                />

                <Insight
                  label="Refunds in last 90 days"
                  value="0"
                />

                <Insight
                  label="Fraud flags"
                  value="0"
                />

                <Insight
                  label="Account risk"
                  value="Low"
                  green
                />

              </div>

            </div>

          </div>

        </div>
      </div>
    </DashboardLayout>
  );
}

function Stat({ title, value, description, color = "text-white" }) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6">
      <p className="text-slate-500">{title}</p>
      <p className={`text-4xl font-bold mt-3 ${color}`}>
        {value}
      </p>
      <p className="text-slate-500 text-sm mt-2">
        {description}
      </p>
    </div>
  );
}

function Insight({ label, value, green = false }) {
  return (
    <div className="flex justify-between items-center border-b border-slate-800 pb-3">
      <span className="text-slate-400">{label}</span>
      <span className={green ? "text-green-400 font-semibold" : "text-white font-semibold"}>
        {value}
      </span>
    </div>
  );
}