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

export default function Scan() {
    const queryClient = useQueryClient();
    const [method, setMethod] = useState<"api" | "sqlite">("api");
    const [selectedLibs, setSelectedLibs] = useState<string[]>([]);
    const [statusFilter, setStatusFilter] = useState<string>("");
    const [mediaFilter, setMediaFilter] = useState<string>("");

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

    // Delete all non-KEEP files mutation
    const deleteAllMutation = useMutation({
        mutationFn: async () => {
            const res = await fetch("/api/scan/delete", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
            });
            const text = await res.text();
            let data: any = null;
            try {
                data = text ? JSON.parse(text) : null;
            } catch {
                // non-JSON response, ignore parsing
            }
            if (!res.ok) {
                throw new Error(data?.detail || "Delete failed");
            }
            return data;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["duplicates"] });
            queryClient.invalidateQueries({ queryKey: ["scan-status"] });
            queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] });
        },
    });

    const handleStartDelete = () => {
        const ok = window.confirm(
            "Are you sure you want to delete all non-KEEP files from the current duplicate sets? This cannot be undone."
        );
        if (!ok) return;
        deleteAllMutation.mutate();
    };

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

    const toggleLib = (title: string) => {
        setSelectedLibs((prev) =>
            prev.includes(title) ? prev.filter((l) => l !== title) : [...prev, title]
        );
    };

    return (
        <div className="space-y-6">
            <h1 className="text-2xl font-bold">Scan & Duplicates</h1>

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

                    {/* Library selection (API method only) */}
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

                        <Button
                            variant="destructive"
                            onClick={handleStartDelete}
                            disabled={deleteAllMutation.isPending}
                        >
                            {deleteAllMutation.isPending ? "Deleting..." : "Start Delete"}
                        </Button>
                    </div>

                    {deleteAllMutation.isError && (
                        <p className="mt-1 text-sm text-red-500">
                            {(deleteAllMutation.error as Error).message}
                        </p>
                    )}
                    {deleteAllMutation.isSuccess && (
                        <p className="mt-1 text-sm text-green-500">
                            Delete completed.
                        </p>
                    )}

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

            {/* Filters */}
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
            </div>

            {/* Duplicate list */}
            {loadingDups ? (
                <p
