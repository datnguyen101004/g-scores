import { Route, BrowserRouter as Router, Routes } from "react-router";
import { ScrollToTop } from "./components/common/ScrollToTop";
import AppLayout from "./layout/AppLayout";
import ScoresDashboard from "./pages/Dashboard/ScoresDashboard";
import ScoreOverview from "./pages/Dashboard/ScoreOverview";
import ScoresReport from "./pages/Report/ScoresReport";
import NotFound from "./pages/OtherPage/NotFound";

export default function App() {
  return (
    <Router>
      <ScrollToTop />
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/" element={<ScoresDashboard />} />
          <Route path="/overview" element={<ScoreOverview />} />
          <Route path="/report" element={<ScoresReport />} />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Routes>
    </Router>
  );
}
