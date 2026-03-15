import { useQuery } from "@tanstack/react-query";
import { statsAPI } from "@/lib/api";
import { formatBytes } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";
import {
  Copy,
  HardDrive,
  FileCheck2,
  Trash2,
  Search,
  BarChart3,
} from "lucide-react";

export default function Dashboard() {
  const { data: stats, isLoading } = useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: statsAPI.getDashboardStats,
    staleTime: 10 * 60 * 1000,
  });

  const { data: history } = useQuery({
    queryKey: ["recent-history"],
    queryFn: () => statsAPI.getHistory(10),
    staleTime: 60 * 1000,
  });

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center text-muted-foreground">
        Loading dashboard...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <Link to="/scan">
          <Button>
            <Search className="mr-2 h-4 w-4" />
            Start Scan
          </Button>
        </Link>
      </div>

      {/* Stats grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Duplicate Sets
            </CardTitle>
            <Copy className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.total_sets ?? 0}</div>
            <p className="text-xs text-muted-foreground">
              {stats?.pending_sets ?? 0} pending review
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Space Reclaimable
            </CardTitle>
            <HardDrive className="h-4 w-4 text-warning" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-warning">
              {formatBytes(stats?.space_reclaimable)}
            </div>
            <p className="text-xs text-muted-foreground">from pending sets</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Space Freed
            </CardTitle>
            <FileCheck2 className="h-4 w-4 text-success" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold text-success">
              {formatBytes(stats?.space_freed)}
            </div>
            <p className="text-xs text-muted-foreground">
              {stats?.processed_sets ?? 0} sets processed
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Total Deletions
            </CardTitle>
            <Trash2 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{stats?.total_deletions ?? 0}</div>
            <p className="text-xs text-muted-foreground">
              {stats?.total_files ?? 0} total files tracked
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Scan method distribution + Recent deletions */}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <BarChart3 className="h-4 w-4" />
              Scan Method Distribution
            </CardTitle>
          </CardHeader>
          <CardContent>
            {stats?.scan_method_distribution &&
            Object.keys(stats.scan_method_distribution).length > 0 ? (
              <div className="space-y-3">
                {Object.entries(stats.scan_method_distribution).map(([method, count]) => {
                  const total = stats.total_sets || 1;
                  const pct = ((count / total) * 100).toFixed(0);
                  return (
                    <div key={method}>
                      <div className="mb-1 flex justify-between text-sm">
                        <span className="capitalize">{method}</span>
                        <span className="text-muted-foreground">
                          {count} ({pct}%)
                        </span>
                      </div>
                      <div className="h-2 rounded-full bg-muted">
                        <div
                          className="h-2 rounded-full bg-primary"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                No scans run yet. Start a scan to see distribution.
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Trash2 className="h-4 w-4" />
              Recent Deletions
            </CardTitle>
          </CardHeader>
          <CardContent>
            {history?.items && history.items.length > 0 ? (
              <div className="space-y-2">
                {history.items.map((item) => (
                  <div
                    key={item.id}
                    className="flex items-center justify-between rounded-md bg-muted/50 px-3 py-2 text-sm"
                  >
                    <span className="min-w-0 truncate text-muted-foreground">
                      {item.file_path?.split("/").pop() ?? "Unknown file"}
                    </span>
                    <div className="flex shrink-0 items-center gap-2">
                      {item.file_size && (
                        <span className="text-xs text-muted-foreground">
                          {formatBytes(item.file_size)}
                        </span>
                      )}
                      <Badge
                        variant={item.error ? "destructive" : "success"}
                        className="text-[10px]"
                      >
                        {item.error ? "Error" : "OK"}
                      </Badge>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No deletions yet.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
