import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { configAPI, setupAPI, scoringAPI, type ScoringRule } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Save, TestTube, Plus, Trash2, ExternalLink, HardDriveDownload } from "lucide-react";

type FolderPriorityRow = {
    id: number;
    path: string;
    file_count?: number;
    priority: "high" | "medium" | "low";
    enabled: boolean;
};

export default function Settings() {
    const queryClient = useQueryClient();
    const [tab, setTab] = useState<"plex" | "arr" | "scoring">("plex");
    const [formValues, setFormValues] = useState<Record<string, string | null>>({});
    const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

    const { data: config } = useQuery({
        queryKey: ["config"],
        queryFn: configAPI.getAll,
        staleTime: 60 * 1000,
    });

    const { data: rules } = useQuery({
        queryKey: ["scoring-rules"],
        queryFn: scoringAPI.getRules,
        staleTime: 60 * 1000,
    });

    useEffect(() => {
        if (config) {
            setFormValues((prev) => ({ ...prev, ...(config as Record<string, string | null>) }));
        }
    }, [config]);

    const saveMutation = useMutation({
        mutationFn: (values: Record<string, string | null>) => configAPI.update(values),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["config"] });
        },
    });

    const testPlexMutation = useMutation({
        mutationFn: setupAPI.testPlex,
        onSuccess: (data) => setTestResult(data),
        onError: (err: Error) => setTestResult({ success: false, message: err.message }),
    });

    const deleteRuleMutation = useMutation({
        mutationFn: scoringAPI.deleteRule,
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ["scoring-rules"] }),
    });

    const [newRule, setNewRule] = useState({
        name: "",
        pattern: "",
        score_modifier: 0,
        enabled: true,
    });
    const createRuleMutation = useMutation({
        mutationFn: () => scoringAPI.createRule(newRule),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["scoring-rules"] });
            setNewRule({ name: "", pattern: "", score_modifier: 0, enabled: true });
        },
    });

    const setField = (key: string, value: string) => {
        setFormValues((prev) => ({ ...prev, [key]: value }));
    };

    const saveConfig = () => {
        const toSave: Record<string, string | null> = {};
        for (const [key, value] of Object.entries(formValues)) {
            if (value !== "********") {
                toSave[key] = value || null;
            }
        }
        saveMutation.mutate(toSave);
    };

    const startOAuth = async () => {
        try {
            const { auth_url, pin_id } = await setupAPI.getPlexAuthUrl();
            window.open(auth_url, "_blank", "width=800,height=600");
            const poll = setInterval(async () => {
                try {
                    const result = await setupAPI.checkPlexAuth(pin_id);
                    if (result.success) {
                        clearInterval(poll);
                        queryClient.invalidateQueries({ queryKey: ["config"] });
                        setTestResult({ success: true, message: "Plex authenticated successfully!" });
                    }
                } catch {
                    // Still waiting
                }
            }, 2000);
            setTimeout(() => clearInterval(poll), 300000);
        } catch (err) {
            setTestResult({ success: false, message: (err as Error).message });
        }
    };

    // Copy Plex DB to local
    const [copyStatus, setCopyStatus] = useState<{ type: "success" | "error"; message: string } | null>(null);
    const copyPlexDbMutation = useMutation({
        mutationFn: async () => {
            const res = await fetch("/api/config/plex-db/copy-local", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
            });
            const text = await res.text();
            let data: any;
            try {
                data = JSON.parse(text);
            } catch {
                throw new Error(`Unexpected response from server: ${text.slice(0, 200)}`);
            }
            if (!res.ok) {
                throw new Error(data?.detail || "Copy failed");
            }
            return data as { local_path: string };
        },
        onSuccess: (data) => {
            setCopyStatus({ type: "success", message: `Copied Plex DB to: ${data.local_path}` });
        },
        onError: (err: Error) => {
            setCopyStatus({ type: "error", message: err.message });
        },
    });

    // Folder priority state
    const [minFolderCount, setMinFolderCount] = useState(10);
    const [folders, setFolders] = useState<FolderPriorityRow[]>([]);
    const [folderScanStatus, setFolderScanStatus] = useState<{
        type: "running" | "success" | "error";
        message: string;
    } | null>(null);

    // Verify Plex DB after saving plex_db_path
    const [dbStatus, setDbStatus] = useState<{ path: string; size_mb: number } | null>(null);
    const [dbStatusError, setDbStatusError] = useState<string | null>(null);
    const verifyPlexDb = async () => {
        setDbStatus(null);
        setDbStatusError(null);
        try {
            const res = await fetch("/api/config/plex-db/status");
            const text = await res.text();
            let data: any = null;
            try {
                data = text ? JSON.parse(text) : null;
            } catch {
                throw new Error(text.slice(0, 200) || "Unexpected non-JSON response from server");
            }

            if (!res.ok) {
                throw new Error(data?.detail || "Failed to verify Plex DB");
            }

            setDbStatus({ path: data.path, size_mb: data.size_mb });
        } catch (err: any) {
            setDbStatusError(err.message || "Failed to verify Plex DB");
        }
    };

    const savePlexDbPathAndVerify = async () => {
        saveConfig();
        await verifyPlexDb();
    };

    // Load existing folder priorities when opening the scoring tab
    useEffect(() => {
        if (tab === "scoring") {
            scoringAPI
                .listFolderPriority()
                .then((data) => setFolders(data))
                .catch(() => { });
        }
    }, [tab]);

    const handleRunFolderScan = async () => {
        try {
            setFolderScanStatus({ type: "running", message: "Scanning Plex DB..." });
            await scoringAPI.scanFolderPriority(minFolderCount);
            const list = await scoringAPI.listFolderPriority();
            setFolders(list);
            setFolderScanStatus({
                type: "success",
                message: `Scan completed: ${list.length} folders loaded`,
            });
        } catch (err: any) {
            setFolderScanStatus({
                type: "error",
                message: err?.message || "Folder scan failed",
            });
        }
    };

    const handleChangePriority = async (row: FolderPriorityRow, priority: "high" | "medium" | "low") => {
        setFolders((rows) =>
            rows.map((r) => (r.id === row.id ? { ...r, priority } : r))
        );
        await scoringAPI.updateFolderPriority(row.id, { priority });
    };

    return (
        <div className="space-y-6">
            <h1 className="text-2xl font-bold">Settings</h1>

            {/* Tabs */}
            <div className="flex gap-2 border-b pb-2">
                {(["plex", "arr", "scoring"] as const).map((t) => (
                    <button
                        key={t}
                        onClick={() => {
                            setTab(t);
                            setTestResult(null);
                            setCopyStatus(null);
                            setDbStatus(null);
                            setDbStatusError(null);
                        }}
                        className={`rounded-t-md px-4 py-2 text-sm font-medium transition-colors ${tab === t
                                ? "bg-primary/10 text-primary"
                                : "text-muted-foreground hover:text-foreground"
                            }`}
                    >
                        {t === "plex" ? "Plex" : t === "arr" ? "Radarr / Sonarr" : "Scoring Rules"}
                    </button>
                ))}
            </div>

            {/* Plex tab */}
            {tab === "plex" && (
                <div className="space-y-4">
                    <Card>
                        <CardHeader>
                            <CardTitle className="text-base">Plex Connection</CardTitle>
                            <CardDescription>Connect to your Plex Media Server</CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div>
                                <Label>Plex URL</Label>
                                <Input
                                    value={formValues.plex_url ?? ""}
                                    onChange={(e) => setField("plex_url", e.target.value)}
                                    placeholder="http://localhost:32400"
                                />
                            </div>
                            <div>
                                <Label>Auth Token</Label>
                                <div className="flex gap-2">
                                    <Input
                                        value={formValues.plex_auth_token ?? ""}
                                        onChange={(e) => setField("plex_auth_token", e.target.value)}
                                        placeholder="Token (use OAuth below)"
                                        type="password"
                                    />
                                    <Button variant="outline" size="sm" onClick={startOAuth}>
                                        <ExternalLink className="mr-2 h-4 w-4" />
                    OAuth
                  </Button>
                                </div>
                            </div>

                            <div className="flex gap-2">
                                <Button onClick={saveConfig} disabled={saveMutation.isPending}>
                                    <Save className="mr-2 h-4 w-4" />
                  Save
                </Button>
                                <Button
                                    variant="outline"
                                    onClick={() => testPlexMutation.mutate()}
                                    disabled={testPlexMutation.isPending}
                                >
                                    <TestTube className="mr-2 h-4 w-4" />
                  Test Connection
                </Button>
                            </div>

                            {testResult && (
                                <Badge variant={testResult.success ? "success" : "destructive"}>
                                    {testResult.message}
                                </Badge>
                            )}
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle className="text-base">SQLite Direct Query</CardTitle>
                            <CardDescription>
                                Path to the Plex database (for advanced duplicate detection) and local copy name
              </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div>
                                <Label>Plex Database Path</Label>
                                <Input
                                    value={formValues.plex_db_path ?? ""}
                                    onChange={(e) => setField("plex_db_path", e.target.value)}
                                    placeholder="/plex-config/.../com.plexapp.plugins.library.db"
                                />
                            </div>
                            <div>
                                <Label>Local Copy File Name</Label>
                                <Input
                                    value={formValues.plex_db_local_name ?? ""}
                                    onChange={(e) => setField("plex_db_local_name", e.target.value)}
                                    placeholder="com.plexapp.plugins.library.db"
                                />
                            </div>
                            <div className="flex flex-wrap gap-2">
                                <Button
                                    onClick={savePlexDbPathAndVerify}
                                    disabled={saveMutation.isPending}
                                    size="sm"
                                >
                                    <Save className="mr-2 h-4 w-4" />
                  Save & Verify
                </Button>
                                <Button
                                    variant="outline"
                                    size="sm"
                                    onClick={() => copyPlexDbMutation.mutate()}
                                    disabled={copyPlexDbMutation.isPending}
                                >
                                    <HardDriveDownload className="mr-2 h-4 w-4" />
                                    {copyPlexDbMutation.isPending ? "Copying..." : "Copy Plex DB to local"}
                                </Button>
                            </div>
                            {dbStatus && (
                                <Badge variant="success" className="mt-2">
                                    Found Plex DB at {dbStatus.path} ({dbStatus.size_mb} MB)
                                </Badge>
                            )}
                            {dbStatusError && (
                                <Badge variant="destructive" className="mt-2">
                                    {dbStatusError}
                                </Badge>
                            )}
                            {copyStatus && (
                                <Badge
                                    variant={copyStatus.type === "success" ? "success" : "destructive"}
                                    className="mt-2"
                                >
                                    {copyStatus.message}
                                </Badge>
                            )}
                        </CardContent>
                    </Card>
                </div>
            )}

            {/* Arr tab */}
            {tab === "arr" && (
                <div className="space-y-4">
                    <Card>
                        <CardHeader>
                            <CardTitle className="text-base">Radarr</CardTitle>
                            <CardDescription>Optional: notify Radarr when files are deleted</CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div>
                                <Label>Radarr URL</Label>
                                <Input
                                    value={formValues.radarr_url ?? ""}
                                    onChange={(e) => setField("radarr_url", e.target.value)}
                                    placeholder="http://localhost:7878"
                                />
                            </div>
                            <div>
                                <Label>API Key</Label>
                                <Input
                                    value={formValues.radarr_api_key ?? ""}
                                    onChange={(e) => setField("radarr_api_key", e.target.value)}
                                    placeholder="API key"
                                    type="password"
                                />
                            </div>
                            <Button onClick={saveConfig} disabled={saveMutation.isPending} size="sm">
                                <Save className="mr-2 h-4 w-4" />
                Save
              </Button>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle className="text-base">Sonarr</CardTitle>
                            <CardDescription>Optional: notify Sonarr when files are deleted</CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div>
                                <Label>Sonarr URL</Label>
                                <Input
                                    value={formValues.sonarr_url ?? ""}
                                    onChange={(e) => setField("sonarr_url", e.target.value)}
                                    placeholder="http://localhost:8989"
                                />
                            </div>
                            <div>
                                <Label>API Key</Label>
                                <Input
                                    value={formValues.sonarr_api_key ?? ""}
                                    onChange={(e) => setField("sonarr_api_key", e.target.value)}
                                    placeholder="API key"
                                    type="password"
                                />
                            </div>
                            <Button onClick={saveConfig} disabled={saveMutation.isPending} size="sm">
                                <Save className="mr-2 h-4 w-4" />
                Save
              </Button>
                        </CardContent>
                    </Card>
                </div>
            )}

            {/* Scoring tab */}
            {tab === "scoring" && (
                <div className="space-y-4">
                    <Card>
                        <CardHeader>
                            <CardTitle className="text-base">Default Scoring</CardTitle>
                            <CardDescription>
                                Built-in scoring: Codec (0-55) + Container (0-40) + Resolution (0-50) + Size (0-30) =
                                max 175
              </CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="grid gap-2 text-sm sm:grid-cols-2">
                                <div className="rounded-md bg-muted/50 px-3 py-2">
                                    <span className="text-green-500">Codec</span>: HEVC=50, H264=30, MPEG4=15, VP9=45
                </div>
                                <div className="rounded-md bg-muted/50 px-3 py-2">
                                    <span className="text-emerald-500">Container</span>: MKV=40, MP4=35, AVI=10
                </div>
                                <div className="rounded-md bg-muted/50 px-3 py-2">
                                    <span className="text-blue-500">Resolution</span>: 4K=50, 1080p=40, 720p=25
                </div>
                                <div className="rounded-md bg-muted/50 px-3 py-2">
                                    <span className="text-purple-500">Size</span>: Smaller = higher (0-30)
                </div>
                            </div>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle className="text-base">Custom Scoring Rules</CardTitle>
                            <CardDescription>
                                Add regex-based rules to adjust scores for specific file patterns
              </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            {rules && rules.length > 0 ? (
                                <div className="space-y-2">
                                    {rules.map((rule: ScoringRule) => (
                                        <div
                                            key={rule.id}
                                            className="flex items-center justify-between rounded-md border px-3 py-2"
                                        >
                                            <div>
                                                <span className="font-medium">{rule.name}</span>
                                                <span className="ml-2 text-xs text-muted-foreground">
                                                    /{rule.pattern}/
                        </span>
                                                <Badge
                                                    variant={rule.score_modifier >= 0 ? "success" : "destructive"}
                                                    className="ml-2"
                                                >
                                                    {rule.score_modifier >= 0 ? "+" : ""}
                                                    {rule.score_modifier}
                                                </Badge>
                                                {!rule.enabled && (
                                                    <Badge variant="secondary" className="ml-1">
                                                        disabled
                                                    </Badge>
                                                )}
                                            </div>
                                            <Button
                                                variant="ghost"
                                                size="icon"
                                                onClick={() => deleteRuleMutation.mutate(rule.id)}
                                            >
                                                <Trash2 className="h-4 w-4" />
                                            </Button>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                    <p className="text-sm text-muted-foreground">No custom rules defined.</p>
                                )}

                            <div className="rounded-md border p-3 space-y-3">
                                <div className="grid gap-3 sm:grid-cols-3">
                                    <div>
                                        <Label>Name</Label>
                                        <Input
                                            value={newRule.name}
                                            onChange={(e) =>
                                                setNewRule((r) => ({ ...r, name: e.target.value }))
                                            }
                                            placeholder="Rule name"
                                        />
                                    </div>
                                    <div>
                                        <Label>Pattern (regex)</Label>
                                        <Input
                                            value={newRule.pattern}
                                            onChange={(e) =>
                                                setNewRule((r) => ({ ...r, pattern: e.target.value }))
                                            }
                                            placeholder="\\.remux\\."
                                        />
                                    </div>
                                    <div>
                                        <Label>Score Modifier</Label>
                                        <Input
                                            type="number"
                                            value={newRule.score_modifier}
                                            onChange={(e) =>
                                                setNewRule((r) => ({
                                                    ...r,
                                                    score_modifier: parseInt(e.target.value) || 0,
                                                }))
                                            }
                                        />
                                    </div>
                                </div>
                                <Button
                                    size="sm"
                                    onClick={() => createRuleMutation.mutate()}
                                    disabled={!newRule.name || !newRule.pattern || createRuleMutation.isPending}
                                >
                                    <Plus className="mr-2 h-4 w-4" />
                  Add Rule
                </Button>
                            </div>
                        </CardContent>
                    </Card>

                    {/* Folder Priority section */}
                    <Card>
                        <CardHeader>
                            <CardTitle className="text-base">Folder Priority</CardTitle>
                            <CardDescription>
                                Prefer files from specific folders when scores are otherwise equal.
              </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div className="flex flex-wrap items-end gap-2">
                                <div>
                                    <Label>Minimum Video File Count</Label>
                                    <Input
                                        type="number"
                                        value={minFolderCount}
                                        onChange={(e) =>
                                            setMinFolderCount(parseInt(e.target.value) || 1)
                                        }
                                        className="w-32"
                                    />
                                </div>
                                <Button
                                    size="sm"
                                    onClick={handleRunFolderScan}
                                    disabled={folderScanStatus?.type === "running"}
                                >
                                    {folderScanStatus?.type === "running" ? "Running..." : "Run"}
                                </Button>
                                {folderScanStatus && (
                                    <span
                                        className={`text-xs ${folderScanStatus.type === "success"
                                                ? "text-green-500"
                                                : folderScanStatus.type === "error"
                                                    ? "text-red-500"
                                                    : "text-muted-foreground"
                                            }`}
                                    >
                                        {folderScanStatus.message}
                                    </span>
                                )}
                            </div>

                            <div className="space-y-2 max-h-80 overflow-auto border rounded-md">
                                {folders.length === 0 ? (
                                    <p className="p-3 text-sm text-muted-foreground">
                                        No folders loaded. Click Run to scan from Plex DB.
                                    </p>
                                ) : (
                                        folders.map((f) => (
                                            <div
                                                key={f.id}
                                                className="flex items-center justify-between border-b px-3 py-2 text-sm"
                                            >
                                                <div className="flex-1 truncate">
                                                    <span className="font-mono">{f.path}</span>
                                                    {typeof f.file_count === "number" && (
                                                        <span className="ml-2 text-xs text-muted-foreground">
                                                            ({f.file_count} files)
                                                        </span>
                                                    )}
                                                </div>
                                                <div className="flex items-center gap-2">
                                                    <select
                                                        value={f.priority}
                                                        onChange={(e) =>
                                                            handleChangePriority(
                                                                f,
                                                                e.target.value as "high" | "medium" | "low"
                                                            )
                                                        }
                                                        className="rounded-md border bg-transparent px-2 py-1 text-xs"
                                                    >
                                                        <option value="high">high</option>
                                                        <option value="medium">medium</option>
                                                        <option value="low">low</option>
                                                    </select>
                                                </div>
                                            </div>
                                        ))
                                    )}
                            </div>
                        </CardContent>
                    </Card>
                </div>
            )}
        </div>
    );
}
