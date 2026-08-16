import { createBrowserRouter, RouterProvider } from "react-router-dom";
import { AppShell } from "./components/AppShell";
import { CurrentPage } from "./pages/CurrentPage";
import { CompaniesPage } from "./pages/CompaniesPage";
import { HistoryPage } from "./pages/HistoryPage";
import { AccountPage } from "./pages/AccountPage";

const router = createBrowserRouter([
  { path: "/", element: <AppShell />, children: [
    { index: true, element: <CurrentPage /> },
    { path: "companies", element: <CompaniesPage /> },
    { path: "history", element: <HistoryPage /> },
    { path: "history/:runId", element: <HistoryPage /> },
    { path: "account", element: <AccountPage /> },
  ] },
]);

export function App() { return <RouterProvider router={router} />; }
