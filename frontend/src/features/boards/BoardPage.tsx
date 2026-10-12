import {
  Badge,
  Button,
  Center,
  Checkbox,
  Group,
  Loader,
  Menu,
  Popover,
  ScrollArea,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { useDebouncedValue, useDisclosure } from "@mantine/hooks";
import { modals } from "@mantine/modals";
import { IconColumns3, IconDots, IconDownload, IconFilter, IconPlus, IconSearch } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import type {
  CellClickedEvent,
  CellKeyDownEvent,
  GridApi,
  GridReadyEvent,
  RowClassParams,
} from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Navigate, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../../shared/api/client";
import { notifyError, useCommand } from "../../shared/api/hooks";
import type { FilterGroup, ItemRow, SavedView, ViewConfig } from "../../shared/api/types";
import { useWorkspace } from "../../shared/workspace";
import { BoardSettingsModal } from "../settings/BoardSettingsModal";
import { BulkBar } from "./BulkBar";
import { buildColumnDefs, readGridState } from "./columns";
import { type CellContext } from "./EditableCell";
import { editStore } from "./editStore";
import { FilterBuilder } from "./FilterBuilder";
import { NewItemModal } from "./NewItemModal";
import { useBoardItems, useUpdateField } from "./useBoardItems";
import { ViewsMenu } from "./ViewsMenu";
import classes from "./board.module.css";

const EMPTY_VIEW: ViewConfig = { columns: [], sort: [], filter: { op: "and", rules: [] }, search: null };

export function BoardPage() {
  const { boardId: boardParam, wsKey } = useParams();
  const { ref, schema, ctx, loading } = useWorkspace();
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();

  const boards = (schema?.boards ?? []).filter((b) => !b.archived);
  // "first" = the board this person used last in this workspace, else the first one.
  const remembered = schema ? localStorage.getItem(`board:${schema.workspace.key}`) : null;
  const board =
    boardParam === "first"
      ? (boards.find((b) => b.id === remembered) ?? boards[0])
      : schema?.boards.find((b) => b.id === boardParam);
  useEffect(() => {
    if (board && schema && !board.archived) localStorage.setItem(`board:${schema.workspace.key}`, board.id);
  }, [board, schema]);

  const viewsQ = useQuery({
    queryKey: ["views", ref?.id, board?.id],
    queryFn: () => api.get<SavedView[]>("/views", { workspace_id: ref!.id, board_id: board!.id }),
    enabled: !!ref && !!board,
  });
  const [viewId, setViewId] = useState<string | null | undefined>(undefined);
  const [config, setConfig] = useState<ViewConfig>(EMPTY_VIEW);
  const [dirty, setDirty] = useState(false);
  const [gridKey, setGridKey] = useState(0);
  const [search, setSearch] = useState("");
  const [debouncedSearch] = useDebouncedValue(search, 250);
  const [selected, setSelected] = useState<ItemRow[]>([]);
  const gridApi = useRef<GridApi<ItemRow> | null>(null);
  const [newOpen, newH] = useDisclosure();
  const [settingsOpen, settingsH] = useDisclosure();

  // Pick the default view (personal default beats shared default) when the board changes.
  useEffect(() => {
    if (!viewsQ.data || viewId !== undefined) return;
    const views = viewsQ.data.filter((v) => v.board_id === board?.id || v.board_id === null);
    const def =
      views.find((v) => v.is_default && v.scope === "personal") ?? views.find((v) => v.is_default) ?? null;
    applyView(def);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewsQ.data, board?.id]);

  useEffect(() => {
    setViewId(undefined);
    setSelected([]);
  }, [board?.id]);

  const applyView = (v: SavedView | null) => {
    setViewId(v?.id ?? null);
    const cfg = v?.config ?? EMPTY_VIEW;
    setConfig({ ...EMPTY_VIEW, ...cfg, filter: cfg.filter ?? { op: "and", rules: [] } });
    setSearch(cfg.search ?? "");
    setDirty(false);
    setGridKey((k) => k + 1);
  };

  const filter = config.filter as FilterGroup;
  const items = useBoardItems(
    { workspaceId: ref?.id ?? "", boardIds: board ? [board.id] : [], filter, search: debouncedSearch },
    !!board,
  );
  const update = useUpdateField();
  const archiveBoard = useCommand("boards.archive", {
    invalidate: [["schema"], ["items"]],
    success: "Board archived",
  });

  const openItem = useCallback(
    (id: string) => {
      params.set("item", id);
      setParams(params);
    },
    [params, setParams],
  );

  const cellContext: CellContext | undefined = useMemo(
    () => (ctx ? { ctx, canEdit: ctx.can("items.update"), update } : undefined),
    [ctx, update],
  );

  const columnDefs = useMemo(() => {
    if (!schema || !ctx || !board) return [];
    const pinnedLeft = schema.workspace.settings?.board?.pinned_left ?? [];
    return buildColumnDefs(schema.columns, config, ctx, {
      onOpen: openItem,
      pinnedLeft,
      boardFields: board.settings?.fields,
    });
    // Rebuild only when the schema/board/saved view changes; live grid edits stay in the grid.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schema, ctx, board, gridKey]);

  const onGridReady = (e: GridReadyEvent<ItemRow>) => {
    gridApi.current = e.api;
  };
  const captureLayout = () => {
    if (!gridApi.current) return;
    const state = readGridState(gridApi.current);
    setConfig((c) => ({ ...c, ...state }));
    setDirty(true);
  };
  const onCellClicked = (e: CellClickedEvent<ItemRow>) => {
    const key = e.column.getColId();
    if (!e.data || key === "name" || key === "status") return;
    editStore.set({ rowId: e.data.id, colKey: key });
  };
  const onCellKeyDown = (e: CellKeyDownEvent<ItemRow>) => {
    const ev = e.event as KeyboardEvent | undefined;
    if (ev?.key === "Enter" && e.data && !editStore.get()) {
      const key = e.column.getColId();
      if (key === "name") openItem(e.data.id);
      else editStore.set({ rowId: e.data.id, colKey: key });
    }
  };

  if (loading || !schema || !ctx) {
    return (
      <Center h="100%">
        <Loader />
      </Center>
    );
  }
  if (!board) {
    if (boards.length)
      return <Navigate to={`/w/${wsKey ?? schema.workspace.key}/b/${boards[0].id}`} replace />;
    return (
      <Center h="100%">
        <Text c="dimmed">This workspace has no boards yet. Create one from the sidebar.</Text>
      </Center>
    );
  }

  const views = (viewsQ.data ?? []).filter((v) => v.board_id === board.id || v.board_id === null);
  const currentView = views.find((v) => v.id === viewId) ?? null;
  const activeFilters = filter?.rules?.length ?? 0;
  const rows = items.data ?? [];

  const exportCsv = () => {
    const state = gridApi.current ? readGridState(gridApi.current) : config;
    const cols = state.columns.filter((c) => !c.hidden).map((c) => c.key);
    api
      .download(
        "/export/items.csv",
        {
          workspace_id: ref!.id,
          board_ids: [board.id],
          filter: activeFilters ? filter : null,
          search: debouncedSearch || null,
          sort: state.sort,
          columns: cols,
        },
        `${board.name} ${new Date().toISOString().slice(0, 10)}.csv`,
      )
      .catch((e) => notifyError(e, "Export failed"));
  };

  return (
    <div className={classes.board}>
      <header className={classes.header}>
        <div>
          <Text size="xs" c="dimmed">
            {schema.workspace.name}
          </Text>
          <Group gap="xs" align="baseline">
            <h1 className={classes.title}>{board.name}</h1>
            <Text size="sm" c="dimmed">
              {items.isFetching && !items.data
                ? "Loading…"
                : `${rows.length} ${rows.length === 1 ? "item" : "items"}`}
            </Text>
          </Group>
        </div>
        <Group gap="xs">
          {ctx.can("items.create") && (
            <Button leftSection={<IconPlus size={16} />} onClick={newH.open}>
              New {schema.workspace.item_label.toLowerCase()}
            </Button>
          )}
          <Menu position="bottom-end" shadow="md">
            <Menu.Target>
              <Button variant="default" px={8} aria-label="Board menu">
                <IconDots size={16} />
              </Button>
            </Menu.Target>
            <Menu.Dropdown>
              <Menu.Item leftSection={<IconDownload size={14} />} onClick={exportCsv}>
                Export CSV (visible columns)
              </Menu.Item>
              {ctx.can("boards.manage") && (
                <>
                  <Menu.Item onClick={settingsH.open}>Board settings</Menu.Item>
                  <Menu.Item
                    color="red"
                    onClick={() =>
                      modals.openConfirmModal({
                        title: `Archive board “${board.name}”?`,
                        children: (
                          <Text size="sm">
                            Its items are archived with it. Restoring the board later brings exactly these
                            items back.
                          </Text>
                        ),
                        labels: { confirm: "Archive board", cancel: "Cancel" },
                        confirmProps: { color: "red" },
                        onConfirm: () =>
                          archiveBoard.mutate(
                            { board_id: board.id },
                            { onSuccess: () => navigate(`/w/${schema.workspace.key}/b/first`) },
                          ),
                      })
                    }
                  >
                    Archive board
                  </Menu.Item>
                </>
              )}
            </Menu.Dropdown>
          </Menu>
        </Group>
      </header>

      <div className={classes.toolbar}>
        <TextInput
          size="xs"
          w={240}
          leftSection={<IconSearch size={14} />}
          placeholder="Search name or client"
          value={search}
          onChange={(e) => {
            setSearch(e.currentTarget.value);
            setConfig((c) => ({ ...c, search: e.currentTarget.value }));
          }}
          aria-label="Search items"
        />
        <Popover position="bottom-start" shadow="lg" withinPortal trapFocus>
          <Popover.Target>
            <Button
              size="xs"
              variant={activeFilters ? "light" : "default"}
              leftSection={<IconFilter size={14} />}
              rightSection={
                activeFilters ? (
                  <Badge size="xs" circle>
                    {activeFilters}
                  </Badge>
                ) : null
              }
            >
              Filter
            </Button>
          </Popover.Target>
          <Popover.Dropdown>
            <FilterBuilder
              value={filter}
              onChange={(f) => {
                setConfig((c) => ({ ...c, filter: f }));
                setDirty(true);
              }}
              columns={schema.columns}
              ctx={ctx}
            />
          </Popover.Dropdown>
        </Popover>
        <ColumnsMenu api={gridApi.current} onChange={captureLayout} />
        <ViewsMenu
          views={views}
          current={currentView}
          dirty={dirty}
          config={{ ...config, search: search || null }}
          workspaceId={ref!.id}
          boardId={board.id}
          canShare={ctx.can("views.shared")}
          onSelect={applyView}
        />
        {dirty && (
          <Button size="xs" variant="subtle" color="gray" onClick={() => applyView(currentView)}>
            Reset
          </Button>
        )}
      </div>

      <div className={`ag-theme-quartz ${classes.grid}`}>
        <AgGridReact<ItemRow>
          key={`${board.id}-${gridKey}`}
          rowData={rows}
          columnDefs={columnDefs}
          context={cellContext}
          getRowId={(p) => p.data.id}
          rowHeight={36}
          headerHeight={36}
          rowSelection={{
            mode: "multiRow",
            checkboxes: true,
            headerCheckbox: true,
            enableClickSelection: false,
          }}
          selectionColumnDef={{ pinned: "left", width: 44 }}
          onSelectionChanged={(e) => setSelected(e.api.getSelectedRows())}
          onGridReady={onGridReady}
          onColumnMoved={(e) => e.finished && captureLayout()}
          onColumnResized={(e) => e.finished && e.source === "uiColumnResized" && captureLayout()}
          onSortChanged={captureLayout}
          onColumnPinned={captureLayout}
          onCellClicked={onCellClicked}
          onCellKeyDown={onCellKeyDown}
          getRowClass={(p: RowClassParams<ItemRow>) =>
            p.data?.highlight_color ? `row-hl-${p.data.highlight_color}` : undefined
          }
          animateRows={false}
          suppressDragLeaveHidesColumns
          suppressColumnVirtualisation
          overlayNoRowsTemplate={
            activeFilters || search ? "No items match the current filters." : "No items on this board yet."
          }
          loading={items.isLoading}
        />
      </div>

      {selected.length > 0 && (
        <BulkBar
          selected={selected}
          ctx={ctx}
          boardId={board.id}
          onClear={() => gridApi.current?.deselectAll()}
        />
      )}
      <NewItemModal opened={newOpen} onClose={newH.close} board={board} ctx={ctx} />
      {settingsOpen && <BoardSettingsModal opened onClose={settingsH.close} board={board} ctx={ctx} />}
    </div>
  );
}

function ColumnsMenu({ api, onChange }: { api: GridApi<ItemRow> | null; onChange: () => void }) {
  const [, force] = useState(0);
  if (!api) return null;
  const cols = api.getColumns()?.filter((c) => c.getColId() !== "ag-Grid-SelectionColumn") ?? [];
  return (
    <Popover position="bottom-start" shadow="lg" withinPortal onOpen={() => force((x) => x + 1)}>
      <Popover.Target>
        <Button size="xs" variant="default" leftSection={<IconColumns3 size={14} />}>
          Columns
        </Button>
      </Popover.Target>
      <Popover.Dropdown>
        <Text size="xs" c="dimmed" mb={6}>
          Drag column headers to reorder. Changes stay until you save or reset the view.
        </Text>
        <ScrollArea.Autosize mah={380}>
          <Stack gap={6}>
            {cols.map((c) => (
              <Checkbox
                key={c.getColId()}
                size="xs"
                label={c.getColDef().headerName}
                checked={c.isVisible()}
                disabled={c.getColId() === "name"}
                onChange={(e) => {
                  api.setColumnsVisible([c.getColId()], e.currentTarget.checked);
                  force((x) => x + 1);
                  onChange();
                }}
              />
            ))}
          </Stack>
        </ScrollArea.Autosize>
      </Popover.Dropdown>
    </Popover>
  );
}
