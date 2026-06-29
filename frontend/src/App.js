import { BrowserRouter, Routes, Route } from "react-router-dom";
import "@/App.css";
import Dashboard from "@/pages/Dashboard";
import Settings from "@/pages/Settings";
import TopBar from "@/components/TopBar";
import { Toaster } from "sonner";

// Module-level constant — avoid re-creating on every render
const TOAST_OPTIONS = {
  style: {
    background: "#0C0E12",
    border: "1px solid #1E2229",
    color: "#FFFFFF",
    borderRadius: 0,
    fontFamily: "IBM Plex Mono, monospace",
  },
};

function Layout({ children }) {
  return (
    <div className="App terminal-scan">
      <TopBar />
      <main className="relative z-10">{children}</main>
    </div>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </Layout>
      <Toaster
        position="bottom-right"
        theme="dark"
        toastOptions={TOAST_OPTIONS}
      />
    </BrowserRouter>
  );
}

export default App;
