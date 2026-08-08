import { useState } from "react";
import DashboardLayout from "../components/layout/DashboardLayout";

export default function Settings() {
  const [notifications, setNotifications] = useState(true);
  const [emailUpdates, setEmailUpdates] = useState(true);
  const [aiInsights, setAiInsights] = useState(true);

  return (
    <DashboardLayout>
      <div className="max-w-5xl mx-auto">

        <div className="mb-8">
          <h1 className="text-4xl font-bold text-white">
            Settings
          </h1>
          <p className="text-slate-400 mt-2">
            Manage your account and application preferences.
          </p>
        </div>

        {/* Account */}
        <section className="bg-slate-900 border border-slate-800 rounded-2xl p-6 mb-6">

          <h2 className="text-xl font-semibold text-white">
            Account
          </h2>

          <p className="text-slate-500 text-sm mt-1">
            Your basic account information.
          </p>

          <div className="grid grid-cols-2 gap-5 mt-6">

            <div>
              <label className="text-slate-400 text-sm">
                Name
              </label>

              <input
                value="Customer"
                readOnly
                className="w-full mt-2 bg-slate-950 border border-slate-700 rounded-xl px-4 py-3 text-white"
              />
            </div>

            <div>
              <label className="text-slate-400 text-sm">
                Customer ID
              </label>

              <input
                value="cc90b054"
                readOnly
                className="w-full mt-2 bg-slate-950 border border-slate-700 rounded-xl px-4 py-3 text-white"
              />
            </div>

          </div>
        </section>

        {/* Notifications */}
        <section className="bg-slate-900 border border-slate-800 rounded-2xl p-6 mb-6">

          <h2 className="text-xl font-semibold text-white">
            Notifications
          </h2>

          <Setting
            title="Complaint notifications"
            description="Receive updates when your complaint status changes."
            enabled={notifications}
            setEnabled={setNotifications}
          />

          <Setting
            title="Email updates"
            description="Receive important updates about your complaints."
            enabled={emailUpdates}
            setEnabled={setEmailUpdates}
          />

        </section>

        {/* AI */}
        <section className="bg-slate-900 border border-slate-800 rounded-2xl p-6 mb-6">

          <h2 className="text-xl font-semibold text-white">
            AI Preferences
          </h2>

          <Setting
            title="AI insights"
            description="Show AI analysis, fraud scores and resolution explanations."
            enabled={aiInsights}
            setEnabled={setAiInsights}
          />

        </section>

        {/* Security */}
        <section className="bg-slate-900 border border-slate-800 rounded-2xl p-6">

          <h2 className="text-xl font-semibold text-white">
            Security
          </h2>

          <div className="flex justify-between items-center mt-5">

            <div>
              <p className="text-white font-medium">
                Account Security
              </p>

              <p className="text-slate-500 text-sm mt-1">
                Your account is protected with authentication.
              </p>
            </div>

            <span className="px-3 py-1 rounded-full bg-green-500/10 text-green-400 text-sm">
              Protected
            </span>

          </div>

        </section>

      </div>
    </DashboardLayout>
  );
}

function Setting({ title, description, enabled, setEnabled }) {
  return (
    <div className="flex justify-between items-center py-5 border-b border-slate-800 last:border-0">

      <div>
        <p className="text-white font-medium">
          {title}
        </p>

        <p className="text-slate-500 text-sm mt-1">
          {description}
        </p>
      </div>

      <button
        onClick={() => setEnabled(!enabled)}
        className={`w-12 h-6 rounded-full transition ${
          enabled ? "bg-blue-600" : "bg-slate-700"
        }`}
      >
        <div
          className={`w-5 h-5 bg-white rounded-full transition transform ${
            enabled ? "translate-x-6" : "translate-x-0.5"
          }`}
        />
      </button>

    </div>
  );
}