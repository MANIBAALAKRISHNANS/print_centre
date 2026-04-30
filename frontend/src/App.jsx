import { BrowserRouter, Routes, Route } from "react-router-dom";

import Sidebar from "./components/Sidebar";
import logo from "./assets/logo.png";
import Dashboard from "./pages/Dashboard";
import Printers from "./pages/Printers";
import Categories from "./pages/Categories";
import Locations from "./pages/Locations";
import Mapping from "./pages/Mapping";
import PrintJobs from "./pages/PrintJobs";
import AppDataProvider from "./context/AppData";

function App() {
  return (
    <AppDataProvider>
      <BrowserRouter>
        <div className="app">
          <Sidebar />

          <div className="main">
            <Routes>
              <Route path="/" element={<Dashboard />} />
              <Route path="/printers" element={<Printers />} />
              <Route path="/categories" element={<Categories />} />
              <Route path="/locations" element={<Locations />} />
              <Route path="/mapping" element={<Mapping />} />
              <Route path="/printjobs" element={<PrintJobs />} />
            </Routes>
          </div>
        </div>
      </BrowserRouter>
    </AppDataProvider>
  );
}

export default App;