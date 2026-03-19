import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { scanAPI, configAPI, type DuplicateSet } from "@/lib/api";
import { formatBytes } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import DuplicateCard from "@/components/DuplicateCard";
import {
    Search,
    RefreshCw,
    Filter,
    Copy,
    HardDrive,
    Clock,
} from "lucide-react";

type DeletionItem = {
    id: number;
    set_id: number;
    title: string;
    file_path: string;
    file_size: number;
    status: "pending" | "deleted";
};

export default function Scan() {
    const queryClient = useQueryClient();
    const [method, setMethod] = useState<"api" | "sqlite">("api");
    const [selectedLibs, setSelectedLibs] = useState<string[]>([]);
    const [statusFilter, setStatusFilter] = useState<string>("");
    const [mediaFilter, setMediaFilter] = useState<string>("");

    const [scanTab, setScanTab] = useState<"duplicates" | "deletions">("duplicates");
    const [deletions, setDeletions] = useState<DeletionItem[]>([]);
    const [deleteRunStatus, setDeleteRunStatus] = useState<string | null>(null);

    const { data: libraries } = useQuery({
        queryKey: ["plex-libraries"],
        queryFn: configAPI.getLibraries,
        staleTime: 5 * 60 * 1000,
        retry: false,
    });

    const { data: duplicates, isLoading: loadingDups } = useQuery({
        queryKey: ["duplicates", statusFilter, mediaFilter],
        queryFn: () =>
            scanAPI.getDuplicates({
                status: statusFilter || undefined,
                media_type: mediaFilter || undefined,
                limit: 100,
            }),
        staleTime: 30 * 1000,
    });

    const { data: scanStatus } = useQuery({
        queryKey: ["scan-status"],
        queryFn: scanAPI.getStatus,
        staleTime: 30 * 1000,
    });

    const scanMutation = useMutation({
        mutationFn: () => scanAPI.startScan(selectedLibs, method),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["duplicates"] });
            queryClient.invalidateQueries({ queryKey: ["scan-status"] });
            queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] });
        },
    });

    const toggleKeepMutation = useMutation({
        mutationFn: ({
            setId,
            fileId,
            keep,
        }: {
            setId: number;
            fileId: number;
            keep: boolean;
        }) => scanAPI.updateFileKeep(setId, fileId, keep),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["duplicates"] });
            queryClient.invalidateQueries({ queryKey: ["scan-status"] });
        },
    });

    // NEW: update set status (pending / approved / rejected)
    const updateSetStatusMutation = useMutation({
        mutationFn: ({
            setId,
            status,
        }: {
            setId: number;
            status: "pending" | "approved" | "rejected";
        }) => scanAPI.updateSetStatus(setId, status),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["duplicates"] });
            queryClient.invalidateQueries({ queryKey: ["scan-status"] });
        },
    });

    const toggleLib = (title: string) => {
        setSelectedLibs((prev) =>
            prev.includes(title) ? prev.filter((l) => l !== title) : [...prev, title]
        );
    };

    const startBulkDelete = async () => {
        const ok = window.confirm(
            "Preview all non-KEEP files that will be deleted?"
        );
        if (!ok) return;

        try {
            setDeleteRunStatus("Loading preview...");
            const res = await fetch("/api/scan/delete/preview");
            const text = await res.text();
            const data = text
                ? JSON.parse(text)
                : { items: [], total_files: 0, total_space_to_free: 0 };

            const items: DeletionItem[] = (data.items || []).map((f: any) => ({
                id: f.id,
                set_id: f.set_id,
                title: f.title,
                file_path: f.file_path,
                file_size: f.file_size,
                status: "pending",
            }));
            setDeletions(items);
            setScanTab("deletions");
            setDeleteRunStatus(
                `Ready: ${data.total_files} files, will free ${formatBytes(
                    data.total_space_to_free || 0
                )}`
            );
        } catch (err: any) {
            setDeleteRunStatus(
                `Preview failed: ${err?.message || String(err)}`
            );
        }
    };

    const runBulkDelete = async () => {
        const ok = window.confirm(
            "Are you sure you want to delete all listed non-KEEP files? This cannot be undone."
        );
        if (!ok) return;

        try {
            setDeleteRunStatus("Deleting...");
            const res = await fetch("/api/scan/delete", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
            });
            const text = await res.text();
            const data = text ? JSON.parse(text) : null;
            if (!res.ok) {
                throw new Error(data?.detail || `Delete failed (${res.status})`);
            }
            const deletedIds = new Set<number>(data?.deleted_file_ids || []);
            setDeletions((items) =>
                items.map((item) =>
                    deletedIds.has(item.id) ? { ...item, status: "deleted" } : item
                )
            );
            setDeleteRunStatus(
                `Deleted ${data?.deleted_files ?? 0} files, freed ${formatBytes(
                    data?.space_freed ?? 0
                )}`
            );
            queryClient.invalidateQueries({ queryKey: ["duplicates"] });
            queryClient.invalidateQueries({ queryKey: ["scan-status"] });
            queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] });
        } catch (err: any) {
            setDeleteRunStatus(
                `Delete failed: ${err?.message || String(err)}`
            );
        }
    };

    return (
        <div className="space-y-6">
            <h1 className="text-2xl font-bold">Scan & Duplicates</h1>

            {/* Local tabs for Duplicates / Deletions */}
            <div className="flex gap-2 border-b pb-2">
                <button
                    onClick={() => setScanTab("duplicates")}
                    className={`rounded-t-md px-3 py-1 text-sm font-medium ${scanTab === "duplicates"
                            ? "bg-primary/10 text-primary"
                            : "text-muted-foreground hover:text-foreground"
                        }`}
                >
                    Duplicates
        </button>
                <button
                    onClick={() => setScanTab("deletions")}
                    className={`rounded-t-md px-3 py-1 text-sm font-medium ${scanTab === "deletions"
                            ? "bg-primary/10 text-primary"
                            : "text-muted-foreground hover:text-foreground"
                        }`}
                >
                    Deletions
        </button>
            </div>

            {/* Scan controls */}
            <Card>
                <CardHeader>
                    <CardTitle className="text-base">Scan Controls</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                    {/* Method selector */}
                    <div>
                        <label className="mb-2 block text-sm text-muted-foreground">
                            Scan Method
            </label>
                        <div className="flex gap-2">
                            <Button
                                variant={method === "api" ? "default" : "outline"}
                                size="sm"
                                onClick={() => setMethod("api")}
                            >
                                Plex API
              </Button>
                            <Button
                                variant={method === "sqlite" ? "default" : "outline"}
                                size="sm"
                                onClick={() => setMethod("sqlite")}
                            >
                                SQLite Direct
              </Button>
                        </div>
                    </div>

                    {/* Library selection */}
                    {method === "api" && libraries && libraries.length > 0 && (
                        <div>
                            <label className="mb-2 block text-sm text-muted-foreground">
                                Libraries (leave empty for all)
              </label>
                            <div className="flex flex-wrap gap-2">
                                {libraries.map((lib) => (
                                    <button
                                        key={lib.key}
                                        onClick={() => toggleLib(lib.title)}
                                        className={`rounded-md border px-3 py-1.5 text-sm transition-colors ${selectedLibs.includes(lib.title)
                                                ? "border-primary bg-primary/20 text-primary"
                                                : "border-border hover:bg-accent"
                                            }`}
                                    >
                                        {lib.title}
                                    </button>
                                ))}
                            </div>
                        </div>
                    )}

                    <div className="flex flex-wrap gap-2">
                        <Button
                            onClick={() => scanMutation.mutate()}
                            disabled={scanMutation.isPending}
                        >
                            {scanMutation.isPending ? (
                                <>
                                    <RefreshCw className="mr-2 h-4 w-4 animate-spin" />
                  Scanning...
                </>
                            ) : (
                                    <>
                                        <Search className="mr-2 h-4 w-4" />
                  Start Scan
                </>
                                )}
                        </Button>

                        <Button variant="destructive" onClick={startBulkDelete}>
                            Start Delete
            </Button>
                    </div>

                    {scanMutation.isSuccess && (
                        <p className="text-sm text-success">
                            Scan complete: {scanMutation.data.sets_found} duplicate sets found (
                            {scanMutation.data.total_files} files)
                        </p>
                    )}
                    {scanMutation.isError && (
                        <p className="text-sm text-destructive-foreground">
                            Scan failed: {(scanMutation.error as Error).message}
                        </p>
                    )}
                </CardContent>
            </Card>

            {/* Status summary */}
            {scanStatus && (
                <div className="grid gap-4 sm:grid-cols-3">
                    <Card>
                        <CardContent className="flex items-center gap-3 p-4">
                            <Copy className="h-5 w-5 text-primary" />
                            <div>
                                <p className="text-lg font-bold">{scanStatus.total_sets ?? 0}</p>
                                <p className="text-xs text-muted-foreground">Duplicate Sets</p>
                            </div>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardContent className="flex items-center gap-3 p-4">
                            <Clock className="h-5 w-5 text-warning" />
                            <div>
                                <p className="text-lg font-bold">
                                    {scanStatus.pending_sets ?? 0}
                                </p>
                                <p className="text-xs text-muted-foreground">Pending Review</p>
                            </div>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardContent className="flex items-center gap-3 p-4">
                            <HardDrive className="h-5 w-5 text-warning" />
                            <div>
                                <p className="text-lg font-bold">
                                    {formatBytes(scanStatus.space_reclaimable ?? 0)}
                                </p>
                                <p className="text-xs text-muted-foreground">
                                    Space Reclaimable
                </p>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            )}

            {scanTab === "duplicates" && (
                <>
                    {/* Filters + Approve All Visible */}
                    <div className="flex flex-wrap items-center gap-3">
                        <Filter className="h-4 w-4 text-muted-foreground" />
                        <select
                            value={statusFilter}
                            onChange={(e) => setStatusFilter(e.target.value)}
                            className="rounded-md border bg-transparent px-3 py-1.5 text-sm"
                        >
                            <option value="">All Statuses</option>
                            <option value="pending">Pending</option>
                            <option value="approved">Approved</option>
                            <option value="processed">Processed</option>
                            <option value="rejected">Rejected</option>
                        </select>
                        <select
                            value={mediaFilter}
                            onChange={(e) => setMediaFilter(e.target.value)}
                            className="rounded-md border bg-transparent px-3 py-1.5 text-sm"
                        >
                            <option value="">All Media</option>
                            <option value="movie">Movies</option>
                            <option value="episode">Episodes</option>
                        </select>

                        <Button
                            size="sm"
                            variant="outline"
                            disabled={!duplicates?.items?.length}
                            onClick={() => {
                                if (!duplicates?.items?.length) return;
                                const ok = window.confirm(
                                    `Approve all ${duplicates.items.length} visible sets?`
                                );
                                if (!ok) return;
                                duplicates.items.forEach((set: DuplicateSet) => {
                                    updateSetStatusMutation.mutate({
                                        setId: set.id,
                                        status: "approved",
                                    });
                                });
                            }}
                        >
                            Approve All Visible
            </Button>
                    </div>

                    {/* Duplicate list */}
                    {loadingDups ? (
                        <p className="text-muted-foreground">Loading duplicates...</p>
                    ) : duplicates?.items && duplicates.items.length > 0 ? (
                        <div className="space-y-3">
                            <p className="text-sm text-muted-foreground">
                                {duplicates.total} duplicate set
                {duplicates.total !== 1 ? "s" : ""}
                            </p>
                            {duplicates.items.map((set: DuplicateSet) => (
                                <DuplicateCard
                                    key={set.id}
                                    set={set}
                                    onToggleKeep={(setId, fileId, keep) =>
                                        toggleKeepMutation.mutate({ setId, fileId, keep })
                                    }
                                    onUpdateStatus={(setId, status) =>
                                        updateSetStatusMutation.mutate({ setId, status })
                                    }
                                />
                            ))}
                        </div>
                    ) : (
                                <Card>
                                    <CardContent className="py-12 text-center">
                                        <Search className="mx-auto mb-3 h-8 w-8 text-muted-foreground" />
                                        <p className="text-muted-foreground">
                                            No duplicates found. Run a scan to detect duplicate files.
                </p>
                                    </CardContent>
                                </Card>
                            )}
                </>
            )}

            {scanTab === "deletions" && (
                <Card>
                    <CardHeader>
                        <CardTitle className="text-base">Deletion Progress</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                        <div className="flex items-center gap-2">
                            <Button
                                size="sm"
                                variant="destructive"
                                onClick={runBulkDelete}
                                disabled={deletions.length === 0}
                            >
                                Run Delete
              </Button>
                            {deleteRunStatus && (
                                <span className="text-xs text-muted-foreground">
                                    {deleteRunStatus}
                                </span>
                            )}
                        </div>

                        <div className="max-h-96 overflow-auto border rounded-md">
                            {deletions.length === 0 ? (
                                <p className="p-3 text-sm text-muted-foreground">
                                    No files queued. Click Start Delete on the Duplicates tab to
                                    load a preview.
                                </p>
                            ) : (
                                    deletions.map((d) => (
                                        <div
                                            key={d.id}
                                            className="flex items-center justify-between border-b px-3 py-2 text-sm"
                                        >
                                            <div className="flex-1 truncate">
                                                <div className="font-medium truncate">{d.title}</div>
                                                <div className="font-mono text-xs truncate text-muted-foreground">
                                                    {d.file_path}
                                                </div>
                                            </div>
                                            <div className="flex items-center gap-2">
                                                <span className="text-xs text-muted-foreground">
                                                    {formatBytes(d.file_size)}
                                                </span>
                                                {d.status === "deleted" ? (
                                                    <span className="text-green-500 text-xs font-semibold">
                                                        ✓
                                                    </span>
                                                ) : (
                                                        <span className="text-yellow-500 text-xs font-semibold">
                                                            …
                                                        </span>
                                                    )}
                                            </div>
                                        </div>
                                    ))
                                )}
                        </div>
                    </CardContent>
                </Card>
            )}
        </div>
    );
}
