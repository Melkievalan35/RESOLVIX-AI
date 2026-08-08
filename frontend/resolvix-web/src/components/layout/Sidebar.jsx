import {
  LayoutDashboard,
  FileText,
  History,
  MessageSquare,
  User,
  Settings,
  LogOut,
  ShieldCheck,
} from "lucide-react";

import { NavLink } from "react-router-dom";

const menus = [
  {
    name: "Dashboard",
    icon: LayoutDashboard,
    path: "/dashboard",
  },
  {
    name: "Complaints",
    icon: FileText,
    path: "/complaint",
  },
  {
    name: "History",
    icon: History,
    path: "/history",
  },
  {
    name: "AI Chat",
    icon: MessageSquare,
    path: "/chat",
  },
  {
    name: "Profile",
    icon: User,
    path: "/profile",
  },
  {
    name: "Settings",
    icon: Settings,
    path: "/settings",
  },
];

export default function Sidebar() {
  return (
    <aside className="w-72 h-screen bg-slate-950 border-r border-slate-800 flex flex-col">

      <div className="px-8 py-8">

        <div className="flex items-center gap-3">

          <div className="w-12 h-12 rounded-xl bg-blue-600 flex items-center justify-center">

            <ShieldCheck size={26} />

          </div>

          <div>

            <h1 className="text-xl font-bold text-white">

              RESOLVIX AI

            </h1>

            <p className="text-xs text-slate-400">

              Complaint Resolution

            </p>

          </div>

        </div>

      </div>

      <div className="px-4 flex-1">

        {menus.map((item) => {

          const Icon = item.icon;

          return (
            <NavLink
              key={item.name}
              to={item.path}
              className={({ isActive }) =>
                `flex items-center gap-4 px-5 py-4 rounded-xl mb-2 transition-all duration-300 ${
                  isActive
                    ? "bg-blue-600 text-white"
                    : "text-slate-400 hover:bg-slate-900 hover:text-white"
                }`
              }
            >
              <Icon size={20} />

              <span>{item.name}</span>
            </NavLink>
          );
        })}
      </div>

      <div className="p-5 border-t border-slate-800">

        <button className="w-full flex items-center justify-center gap-3 bg-red-600 hover:bg-red-700 transition rounded-xl py-3">

          <LogOut size={18} />

          Logout

        </button>

      </div>

    </aside>
  );
}