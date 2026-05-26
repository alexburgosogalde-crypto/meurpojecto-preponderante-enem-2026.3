import { useEffect } from "react";
import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";

const Redirect = ({ to }) => {
  useEffect(() => { window.location.replace(to); }, [to]);
  return null;
};

function App() {
  return (
    <div className="App">
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Redirect to="/home.html" />} />
          <Route path="/donaspainel" element={<Redirect to="/donaspainel.html" />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </div>
  );
}

export default App;
