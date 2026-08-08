import Navbar from "./Navbar";
import Sidebar from "./Sidebar";

export default function PageLayout({ children }) {
  return (
    <>
      <Navbar />

      <div
        style={{
          display: "flex",
        }}
      >
        <Sidebar />

        <div
          style={{
            flex: 1,
            padding: "40px",
            background: "#F8FAFC",
            minHeight: "100vh",
          }}
        >
          {children}
        </div>
      </div>
    </>
  );
}