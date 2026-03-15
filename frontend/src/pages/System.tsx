import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { systemAPI } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { RefreshCw, Terminal, Info } from "lucide-react";

function colorLog(line: string) {
  if (line.includes(" ERROR ")) return "text-red-400";
  if (line.includes(" WARNING ")) return "text-amber-400";
  if (line.includes(" DEBUG ")) return "text-gray-500";
  return "text-foreground";
}

export default function System() {
  const [logLimit, setLogLimit] = useState(100);

  const { data: version } = useQuery({
    queryKey: ["version"],
    queryFn: systemAPI.getVersion,
    staleTime: 60 * 60 * 1000,
  });

  const {
    data: logs,
    refetch: refetchLogs,
    isFetching: loadingLogs,
  } = useQuery({
    queryKey: ["logs", logLimit],
    queryFn: () => systemAPI.getLogs(logLimit),
    staleTime: 10 * 1000,
  });

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">System</h1>

      {/* Version info */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Info className="h-4 w-4" />
            Application Info
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-md bg-muted/50 px-4 py-3">
              <p className="text-xs text-muted-foreground">App Name</p>
              <p className="font-medium">{version?.app_name ?? "DeDuparr"}</p>
            </div>
            <div className="rounded-md bg-muted/50 px-4 py-3">
              <p className="text-xs text-muted-foreground">Version</p>
              <p className="font-medium">{version?.version ?? "—"}</p>
            </div>
            <div className="rounded-md bg-muted/50 px-4 py-3">
              <p className="text-xs text-muted-foreground">Status</p>
              <Badge variant="success">Running</Badge>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Logs */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-base">
              <Terminal className="h-4 w-4" />
              Application Logs
            </CardTitle>
            <div className="flex items-center gap-2">
              <select
                value={logLimit}
                onChange={(e) => setLogLimit(Number(e.target.value))}
                className="rounded-md border bg-transparent px-2 py-1 text-sm"
              >
                <option value={50}>50 lines</option>
                <option value={100}>100 lines</option>
                <option value={200}>200 lines</option>
                <option value={500}>500 lines</option>
              </select>
              <Button
                variant="outline"
                size="sm"
                onClick={() => refetchLogs()}
                disabled={loadingLogs}
              >
                <RefreshCw className={`mr-2 h-4 w-4 ${loadingLogs ? "animate-spin" : ""}`} />
                Refresh
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <div className="max-h-[500px] overflow-auto rounded-md bg-black/50 p-4 font-mono text-xs">
            {logs?.lines && logs.lines.length > 0 ? (
              logs.lines.map((line, i) => (
                <div key={i} className={colorLog(line)}>
                  {line}
                </div>
              ))
            ) : (
              <p className="text-muted-foreground">No log entries.</p>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
