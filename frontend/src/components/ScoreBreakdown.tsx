import type { FileMetadata } from "@/lib/api";

interface ScoreBreakdownProps {
  metadata: FileMetadata | null;
  totalScore: number;
}

const MAX_SCORE = 175;

function Bar({ value, max, color, label }: { value: number; max: number; color: string; label: string }) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0;
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-20 text-muted-foreground">{label}</span>
      <div className="h-2 flex-1 rounded-full bg-muted">
        <div
          className={`h-2 rounded-full ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="w-8 text-right font-mono text-muted-foreground">{value}</span>
    </div>
  );
}

export default function ScoreBreakdown({ metadata, totalScore }: ScoreBreakdownProps) {
  const codecScore = metadata?.codec_score ?? 0;
  const containerScore = metadata?.container_score ?? 0;
  const resolutionScore = metadata?.resolution_score ?? 0;
  const sizeScore = metadata?.size_score ?? 0;

  const totalPct = Math.min((totalScore / MAX_SCORE) * 100, 100);

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-sm">
        <span className="font-medium">Score: {totalScore}/{MAX_SCORE}</span>
        <span className="text-xs text-muted-foreground">{totalPct.toFixed(0)}%</span>
      </div>
      <Bar value={codecScore} max={55} color="bg-green-500" label="Codec" />
      <Bar value={containerScore} max={40} color="bg-emerald-500" label="Container" />
      <Bar value={resolutionScore} max={50} color="bg-blue-500" label="Resolution" />
      <Bar value={sizeScore} max={30} color="bg-purple-500" label="Size" />
    </div>
  );
}
