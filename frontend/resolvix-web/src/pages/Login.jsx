import { useState } from "react";
import { Eye, EyeOff, Mail, Lock } from "lucide-react";
import { login } from "../services/auth";
import { useNavigate, Link } from "react-router-dom";

export default function Login() {
  const navigate = useNavigate();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleLogin = async (e) => {
    e.preventDefault();

    setLoading(true);
    setError("");

    try {
      const data = await login(email, password);


      navigate("/dashboard");
    } catch (err) {
      setError(
        err.response?.data?.detail || "Invalid email or password."
      );
    }

    setLoading(false);
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-950">

      <div className="w-full max-w-md bg-slate-900 rounded-2xl shadow-2xl p-8">

        <h1 className="text-4xl font-bold text-center text-blue-500">
          RESOLVIX AI
        </h1>

        <p className="text-center text-gray-400 mt-2">
          AI Powered Complaint Resolution
        </p>

        {error && (
          <div className="bg-red-500/20 border border-red-500 text-red-300 rounded-lg p-3 mt-6">
            {error}
          </div>
        )}

        <form onSubmit={handleLogin} className="mt-8">

          <div className="mb-5">

            <label className="block mb-2 text-gray-300">
              Email
            </label>

            <div className="flex items-center bg-slate-800 rounded-lg px-3">

              <Mail size={18} className="text-gray-400" />

              <input
                type="email"
                className="w-full bg-transparent outline-none p-3"
                placeholder="kapil@gmail.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />

            </div>

          </div>

          <div className="mb-6">

            <label className="block mb-2 text-gray-300">
              Password
            </label>

            <div className="flex items-center bg-slate-800 rounded-lg px-3">

              <Lock size={18} className="text-gray-400" />

              <input
                type={showPassword ? "text" : "password"}
                className="w-full bg-transparent outline-none p-3"
                placeholder="********"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />

              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
              >
                {showPassword ? (
                  <EyeOff size={18} />
                ) : (
                  <Eye size={18} />
                )}
              </button>

            </div>

          </div>

          <button
            className="w-full bg-blue-600 hover:bg-blue-700 rounded-lg p-3 font-semibold transition"
            disabled={loading}
          >
            {loading ? "Logging in..." : "Login"}
          </button>

        </form>

        <p className="text-center mt-6 text-gray-400">
          Don't have an account?{" "}
          <Link
            to="/register"
            className="text-blue-400 hover:underline"
          >
            Register
          </Link>
        </p>

      </div>

    </div>
  );
}