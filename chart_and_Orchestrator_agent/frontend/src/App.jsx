import { BrowserRouter, Routes, Route } from "react-router-dom";
import Generate from "./pages/Generate";
import Chat from "./pages/Chat";
import Search from "./pages/Search";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* when you go to http://localhost:5173/generate */}
        <Route path="/generate" element={<Generate />} />
        <Route path="/chat" element={<Chat />} />
        <Route path="/search" element={<Search />} />

      </Routes>
    </BrowserRouter>
  );
}
