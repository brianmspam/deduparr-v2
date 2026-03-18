import { useState, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { configAPI, setupAPI, scoringAPI, type ScoringRule } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Save, TestTube, Plus, Trash2, ExternalLink, HardDriveDownload } from "lucide-react";

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

  // NEW: copy Plex DB to local
  const [copyStatus, setCopyStatus] = useState<{ type: "success" | "error"; message: string } | null>(null);
  const copyPlexDbMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch("/api/config/plex-db/copy-local", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      const data = await res.json();
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
            }}
            className={`rounded-t-md px-4 py-2 text-sm font-medium transition-colors ${
              tab === t
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
                Path to a copy of the Plex database (for advanced duplicate detection)
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <Label>Plex Database Path</Label>
                <Input
                  value={formValues.plex_db_path ?? ""}
                  onChange={(e) => setField("plex_db_path", e.target.value)}
                  placeholder="/plex-config/Library/Application Support/Plex Media Server/Plug-in Support/Databases/com.plexapp.plugins.library.db"
                />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button onClick={saveConfig} disabled={saveMutation.isPending}
