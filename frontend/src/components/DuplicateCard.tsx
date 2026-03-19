import { useState } from "react";
import type { DuplicateSet } from "@/lib/api";
import { formatBytes } from "@/lib/utils";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import FileComparison from "./FileComparison";
import { ChevronDown, ChevronRight, Film, Tv, Trash2 } from "lucide-react";

interface DuplicateCardProps {
    set: DuplicateSet;
    onToggleKeep?: (setId: number, fileId: number, keep: boolean) => void;
    onDelete?: (setId: number) => void;
    onUpdateStatus?: (
        setId: number,
        status: "pending" | "approved" | "rejected"
    ) => void;
}

function statusVariant(status: string | null) {
    switch (status) {
        case "pending":
            return "warning" as const;
        case "processed":
            return "success" as const;
        case "approved":
            return "default" as const;
        case "rejected":
            return "secondary" as const;
        default:
            return "outline" as const;
    }
}

export default function DuplicateCard({
    set,
    onToggleKeep,
    onDelete,
    onUpdateStatus,
}: DuplicateCardProps) {
    const [expanded, setExpanded] = useState(false);

    return (
        <div className="rounded-lg border bg-card">
            <button
                onClick={() => setExpanded(!expanded)}
                className="flex w-full items-center gap-3 p-4 text-left transition-colors hover:bg-accent/50"
            >
                {expanded ? (
                    <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
                ) : (
                        <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
                    )}

                <div className="flex min-w-0 flex-1 items-center gap-3">
                    {set.media_type === "movie" ? (
                        <Film className="h-4 w-4 shrink-0 text-blue-400" />
                    ) : (
                            <Tv className="h-4 w-4 shrink-0 text-purple-400" />
                        )}
                    <span className="truncate font-medium">{set.title}</span>
                </div>

                <div className="flex shrink-0 items-center gap-2">
                    <Badge variant={statusVariant(set.status)}>
                        {set.status ?? "unknown"}
                    </Badge>
                    {set.scan_method && <Badge variant="outline">{set.scan_method}</Badge>}
                    <span className="text-xs text-muted-foreground">
                        {set.files.length} files
          </span>
                    <span className="text-xs font-medium text-warning">
                        {formatBytes(set.space_to_reclaim)}
                    </span>

                    {onUpdateStatus && (
                        <div className="ml-2 flex items-center gap-1">
                            <Button
                                size="xs"
                                variant={set.status === "approved" ? "default" : "outline"}
                                onClick={(e) => {
                                    e.stopPropagation();
                                    onUpdateStatus(set.id, "approved");
                                }}
                            >
                                Approve
              </Button>
                            <Button
                                size="xs"
                                variant={set.status === "rejected" ? "destructive" : "outline"}
                                onClick={(e) => {
                                    e.stopPropagation();
                                    onUpdateStatus(set.id, "rejected");
                                }}
                            >
                                Reject
              </Button>
                        </div>
                    )}
                </div>
            </button>

            {expanded && (
                <div className="border-t px-4 py-4">
                    <FileComparison
                        files={set.files}
                        onToggleKeep={
                            onToggleKeep
                                ? (fileId, keep) => onToggleKeep(set.id, fileId, keep)
                                : undefined
                        }
                    />

                    {onDelete && set.status === "pending" && (
                        <div className="mt-4 flex justify-end">
                            <Button
                                variant="destructive"
                                size="sm"
                                onClick={() => onDelete(set.id)}
                            >
                                <Trash2 className="mr-2 h-4 w-4" />
                Delete Duplicates
              </Button>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
