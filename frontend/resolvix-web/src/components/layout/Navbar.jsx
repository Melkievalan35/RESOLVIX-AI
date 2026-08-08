export default function Navbar() {
  return (
    <div className="h-20 border-b border-slate-800 bg-slate-950 flex items-center justify-between px-8">

      <div>

        <h2 className="text-3xl font-bold">

          Dashboard

        </h2>

        <p className="text-slate-400">

          Welcome back 👋

        </p>

      </div>

      <div className="flex items-center gap-4">

        <div className="text-right">

          <p className="font-semibold">

            Kapil

          </p>

          <p className="text-sm text-slate-400">

            Customer

          </p>

        </div>

        <img
          src="https://ui-avatars.com/api/?name=Kapil"
          className="w-12 h-12 rounded-full"
        />

      </div>

    </div>
  );
}