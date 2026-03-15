import type { DuplicateFile } from "@/lib/api";
import { formatBytes } from "@/lib/utils";
import ScoreBreakdown from "./ScoreBreakdown";
import { Badge } from "./ui/badge";
import { Check, Trash2 } from "lucide-react";

interface FileComparisonProps {
  files: DuplicateFile[];
  onToggleKeep?: (fileId: number, keep: boolean) => void;
}

export default function FileComparison({ files, onToggleKeep }: FileComparisonProps) {
  const sorted = [...files].sort((a, b) => b.score - a.score);
  const bestScore = sorted[0]?.score ?? 0;

  return (
    <div className="space-y-3">
      {sorted.map((file, idx) => {
        const isBest = file.score === bestScore && idx === 0;
        const meta = file.file_metadata;
        return (
          <div
            key={file.id}
            className={`rounded-lg border p-4 transition-colors ${
              file.keep
                ? "border-green-500/30 bg-green-500/5"
                : "border-destructive/30 bg-destructive/5"
            }`}
          >
            <div className="mb-3 flex items-start justify-between gap-2">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  {isBest && <Badge variant="success">Recommended</Badge>}
                  <Badge variant={file.keep ? "success" : "destructive"}>
                    {file.keep ? "Keep" : "Delete"}
                  </Badge>
                </div>
                <p className="mt-1 break-all text-sm text-muted-foreground">{file.file_path}</p>
              </div>
              {onToggleKeep && (
                <button
                  onClick={() => onToggleKeep(file.id, !file.keep)}
                  className={`shrink-0 rounded-md p-2 transition-colors ${
                    file.keep
                      ? "bg-green-500/20 text-green-500 hover:bg-green-500/30"
                      : "bg-destructive/20 text-destructive-foreground hover:bg-destructive/30"
                  }`}
                  title={file.keep ? "Mark for deletion" : "Mark to keep"}
                >
                  {file.keep ? <Check className="h-4 w-4" /> : <Trash2 className="h-4 w-4" />}
                </button>
              )}
            </div>

            <div className="mb-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
              <div>
                <span className="text-muted-foreground">Size:</span>{" "}
                <span className="font-medium">{formatBytes(file.file_size)}</span>
              </div>
              {meta?.codec && (
                <div>
                  <span className="text-muted-foreground">Codec:</span>{" "}
                  <span className="font-medium">{meta.codec}</span>
                </div>
              )}
              {meta?.container && (
                <div>
                  <span className="text-muted-foreground">Container:</span>{" "}
                  <span className="font-medium">{meta.container}</span>
                </div>
              )}
              {meta?.resolution && (
                <div>
                  <span className="text-muted-foreground">Resolution:</span>{" "}
                  <span className="font-medium">{meta.resolution}</span>
                </div>
              )}
            </div>

            <ScoreBreakdown metadata={meta} totalScore={file.score} />
          </div>
        );
      })}
    </div>
  );
}
