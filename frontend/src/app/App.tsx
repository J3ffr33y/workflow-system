import { MantineProvider } from "@mantine/core";
import { DatesProvider } from "@mantine/dates";
import { ModalsProvider } from "@mantine/modals";
import { Notifications } from "@mantine/notifications";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "dayjs/locale/en-au";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { ApiError } from "../shared/api/client";
import { ActivityPage } from "../features/activity/ActivityPage";
import { ArchivedPage } from "../features/archive/ArchivedPage";
import { LoginPage } from "../features/auth/LoginPage";
import { AutomationRunsPage } from "../features/automations/AutomationRunsPage";
import { AutomationsPage } from "../features/automations/AutomationsPage";
import { BoardPage } from "../features/boards/BoardPage";
import { ClientPage } from "../features/clients/ClientPage";
import { ClientsPage } from "../features/clients/ClientsPage";
import { HomePage } from "../features/home/HomePage";
import { MigrationPage } from "../features/migration/MigrationPage";
import { MigrationRunPage } from "../features/migration/MigrationRunPage";
import { SettingsPage } from "../features/settings/SettingsPage";
import { SystemPage } from "../features/settings/SystemPage";
import { UsersPage } from "../features/settings/UsersPage";
import { WorkspaceSetupPage } from "../features/settings/WorkspaceSetupPage";
import { Layout } from "./Layout";
import { theme } from "./theme";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: true,
      retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 2,
    },
  },
});

export function App() {
  return (
    <MantineProvider theme={theme}>
      <DatesProvider settings={{ locale: "en-au", firstDayOfWeek: 1 }}>
        <QueryClientProvider client={queryClient}>
          <ModalsProvider>
            <Notifications position="bottom-right" />
            <BrowserRouter>
              <Routes>
                <Route path="/login" element={<LoginPage />} />
                <Route element={<Layout />}>
                  <Route index element={<Navigate to="/home" replace />} />
                  <Route path="/home" element={<HomePage />} />
                  <Route path="/w/:wsKey/b/:boardId" element={<BoardPage />} />
                  <Route path="/w/:wsKey/archived" element={<ArchivedPage />} />
                  <Route path="/w/:wsKey/automations" element={<AutomationsPage />} />
                  <Route path="/w/:wsKey/automations/runs" element={<AutomationRunsPage />} />
                  <Route path="/w/:wsKey/setup" element={<WorkspaceSetupPage />} />
                  <Route path="/w/:wsKey/migration" element={<MigrationPage />} />
                  <Route path="/w/:wsKey/migration/:runId" element={<MigrationRunPage />} />
                  <Route path="/clients" element={<ClientsPage />} />
                  <Route path="/clients/:clientId" element={<ClientPage />} />
                  <Route path="/activity" element={<ActivityPage />} />
                  <Route path="/users" element={<UsersPage />} />
                  <Route path="/settings" element={<SettingsPage />} />
                  <Route path="/system" element={<SystemPage />} />
                  <Route path="*" element={<Navigate to="/home" replace />} />
                </Route>
              </Routes>
            </BrowserRouter>
          </ModalsProvider>
        </QueryClientProvider>
      </DatesProvider>
    </MantineProvider>
  );
}
