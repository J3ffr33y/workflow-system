import { AppShell, Burger, Center, Group, Loader, ScrollArea, Text, UnstyledButton } from "@mantine/core";
import { useDisclosure } from "@mantine/hooks";
import {
  IconActivity,
  IconArchive,
  IconBolt,
  IconBuildingStore,
  IconDatabaseImport,
  IconHeartbeat,
  IconHome,
  IconLayoutKanban,
  IconLogout,
  IconPlus,
  IconSettings,
  IconTable,
  IconUsers,
} from "@tabler/icons-react";
import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Navigate, NavLink, Outlet, useLocation, useNavigate, useParams } from "react-router-dom";
import { ItemDrawer } from "../features/items/ItemDrawer";
import { NotificationBell } from "../features/notifications/NotificationBell";
import { CreateBoardButton } from "../features/settings/CreateBoardButton";
import { api, setCsrf } from "../shared/api/client";
import { useMe, useSchema } from "../shared/api/hooks";
import { useRealtime } from "../shared/realtime";
import { ErrorBoundary } from "../shared/ui/ErrorBoundary";
import classes from "./Layout.module.css";

function Item({ to, icon, label, end }: { to: string; icon: React.ReactNode; label: string; end?: boolean }) {
  return (
    <NavLink
      to={to}
      end={end}
      className={({ isActive }) => `${classes.link} ${isActive ? classes.active : ""}`}
    >
      {icon}
      <span className={classes.linkLabel}>{label}</span>
    </NavLink>
  );
}

export function Layout() {
  const { t } = useTranslation();
  const me = useMe();
  const [opened, { toggle, close }] = useDisclosure();
  const params = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const qc = useQueryClient();
  useRealtime(!!me.data);

  const last = localStorage.getItem("ws") ?? undefined;
  const wsKey = params.wsKey ?? last ?? me.data?.workspaces[0]?.key;
  const ws = me.data?.workspaces.find((w) => w.key === wsKey) ?? me.data?.workspaces[0];
  const schema = useSchema(ws?.id);
  if (params.wsKey && ws) localStorage.setItem("ws", ws.key);

  if (me.isLoading) {
    return (
      <Center h="100vh">
        <Loader />
      </Center>
    );
  }
  if (me.isError || !me.data) return <Navigate to="/login" state={{ from: location.pathname }} replace />;

  const perms = new Set(ws?.permissions ?? []);
  const boards = (schema.data?.boards ?? []).filter((b) => !b.archived);

  const logout = async () => {
    await api.post("/auth/logout");
    setCsrf(null);
    qc.clear();
    navigate("/login");
  };

  return (
    <AppShell
      navbar={{ width: 248, breakpoint: "sm", collapsed: { mobile: !opened } }}
      header={{ height: { base: 48, sm: 0 } }}
      padding={0}
    >
      <AppShell.Header hiddenFrom="sm" className={classes.mobileHeader}>
        <Group h="100%" px="md">
          <Burger opened={opened} onClick={toggle} size="sm" color="white" aria-label="Menu" />
          <Text c="white" fw={600}>
            Workflow
          </Text>
        </Group>
      </AppShell.Header>
      <AppShell.Navbar
        className={classes.nav}
        onClick={(e) => (e.target as HTMLElement).closest("a") && close()}
      >
        <div className={classes.brand}>
          <span className={classes.mark} aria-hidden />
          <Text fw={600} c="white" size="md">
            Workflow
          </Text>
          <div style={{ flex: 1 }} />
          <NotificationBell />
        </div>

        {me.data.workspaces.length > 1 && (
          <div className={classes.switcher} role="tablist" aria-label="Product line">
            {me.data.workspaces.map((w) => (
              <UnstyledButton
                key={w.key}
                role="tab"
                aria-selected={w.key === ws?.key}
                className={`${classes.switch} ${w.key === ws?.key ? classes.switchOn : ""}`}
                onClick={() => {
                  localStorage.setItem("ws", w.key);
                  // "first" resolves to the workspace's first board.
                  navigate(`/w/${w.key}/b/first`);
                }}
              >
                {w.name.replace(/^Smart /, "")}
              </UnstyledButton>
            ))}
          </div>
        )}

        <ScrollArea className={classes.scroll} type="hover">
          <Item to="/home" icon={<IconHome size={17} />} label={t("nav.home")} />
          <div className={classes.section}>
            <span>{t("nav.boards")}</span>
            {ws && perms.has("boards.manage") && schema.data && (
              <CreateBoardButton workspaceId={ws.id}>
                <IconPlus size={14} />
              </CreateBoardButton>
            )}
          </div>
          {ws &&
            boards.map((b) => (
              <Item
                key={b.id}
                to={`/w/${ws.key}/b/${b.id}`}
                icon={<IconLayoutKanban size={17} />}
                label={b.name}
              />
            ))}
          {ws && (
            <>
              <Item to={`/w/${ws.key}/archived`} icon={<IconArchive size={17} />} label={t("nav.archived")} />
              <div className={classes.section}>
                <span>{ws.name}</span>
              </div>
              <Item
                to={`/w/${ws.key}/automations`}
                end
                icon={<IconBolt size={17} />}
                label={t("nav.automations")}
              />
              <Item
                to={`/w/${ws.key}/automations/runs`}
                icon={<IconTable size={17} />}
                label={t("nav.automationLogs")}
              />
              {perms.has("schema.manage") && (
                <Item
                  to={`/w/${ws.key}/setup`}
                  icon={<IconSettings size={17} />}
                  label={t("nav.workspaceSettings")}
                />
              )}
              {perms.has("migration.run") && (
                <Item
                  to={`/w/${ws.key}/migration`}
                  icon={<IconDatabaseImport size={17} />}
                  label={t("nav.migration")}
                />
              )}
            </>
          )}
          <div className={classes.section}>
            <span>Company</span>
          </div>
          <Item to="/clients" icon={<IconBuildingStore size={17} />} label={t("nav.clients")} />
          <Item to="/activity" icon={<IconActivity size={17} />} label={t("nav.activity")} />
          {me.data.is_superadmin && (
            <Item to="/users" icon={<IconUsers size={17} />} label={t("nav.users")} />
          )}
          {me.data.is_superadmin && (
            <Item to="/system" icon={<IconHeartbeat size={17} />} label={t("nav.system")} />
          )}
        </ScrollArea>

        <div className={classes.footer}>
          <NavLink to="/settings" className={classes.user}>
            <Text size="sm" c="white" truncate>
              {me.data.user.full_name}
            </Text>
            <Text size="xs" c="gray.5" truncate>
              {me.data.user.email}
            </Text>
          </NavLink>
          <UnstyledButton
            className={classes.iconBtn}
            onClick={logout}
            aria-label={t("nav.logout")}
            title={t("nav.logout")}
          >
            <IconLogout size={17} />
          </UnstyledButton>
        </div>
      </AppShell.Navbar>
      <AppShell.Main className={classes.main}>
        <ErrorBoundary key={location.pathname}>
          <Outlet />
        </ErrorBoundary>
        <ItemDrawer />
      </AppShell.Main>
    </AppShell>
  );
}
