const BASE_URL = import.meta.env.VITE_API_URL ?? "";

function extractErrorMessage(body: Record<string, unknown>, status: number): string {
  const detail = body.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    // FastAPI validation errors: [{"msg": "...", "loc": [...], "type": "..."}]
    return detail.map((d: Record<string, unknown>) => d.msg ?? JSON.stringify(d)).join("; ");
  }
  if (typeof detail === "object" && detail !== null) return JSON.stringify(detail);
  return `Request failed: ${status}`;
}

async function fetchAPI<T>(endpoint: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${endpoint}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(body, res.status));
  }
  return res.json();
}

async function postAPI<T, U = unknown>(endpoint: string, data?: U): Promise<T> {
  const res = await fetch(`${BASE_URL}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: data !== undefined ? JSON.stringify(data) : undefined,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(body, res.status));
  }
  return res.json();
}

async function putAPI<T, U = unknown>(endpoint: string, data: U): Promise<T> {
  const res = await fetch(`${BASE_URL}${endpoint}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(body, res.status));
  }
  return res.json();
}

async function patchAPI<T, U = unknown>(endpoint: string, data: U): Promise<T> {
  const res = await fetch(`${BASE_URL}${endpoint}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(body, res.status));
  }
  return res.json();
}

async function deleteAPI<T>(endpoint: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${endpoint}`, { method: "DELETE" });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(extractErrorMessage(body, res.status));
  }
  return res.json();
}

// --- Types ---

export interface DashboardStats {
  total_sets: number;
  pending_sets: number;
  processed_sets: number;
  space_reclaimable: number;
  space_freed: number;
  total_files: number;
  total_deletions: number;
  scan_method_distribution: Record<string, number>;
}

export interface DuplicateFile {
  id: number;
  file_path: string;
  file_size: number;
  score: number;
  keep: boolean;
  file_metadata: FileMetadata | null;
}

export interface FileMetadata {
  codec?: string;
  container?: string;
  resolution?: string;
  width?: number;
  height?: number;
  bitrate?: number;
  codec_score?: number;
  container_score?: number;
  resolution_score?: number;
  size_score?: number;
}

export interface DuplicateSet {
  id: number;
  plex_item_id: string | null;
  title: string;
  media_type: string | null;
  found_at: string | null;
  status: string | null;
  space_to_reclaim: number;
  scan_method: string | null;
  files: DuplicateFile[];
}

export interface DuplicatesResponse {
  total: number;
  items: DuplicateSet[];
}

export interface HistoryItem {
  id: number;
  duplicate_file_id: number;
  file_path: string | null;
  file_size: number | null;
  deleted_at: string | null;
  deleted_from_disk: boolean;
  plex_refreshed: boolean;
  deleted_from_arr: boolean;
  error: string | null;
}

export interface HistoryResponse {
  total: number;
  items: HistoryItem[];
}

export interface ScoringRule {
  id: number;
  name: string;
  pattern: string;
  score_modifier: number;
  enabled: boolean;
  created_at?: string;
}

export interface PlexLibrary {
  key: string;
  title: string;
  type: string;
}

export interface VersionInfo {
  version: string;
  app_name: string;
}

export interface LogsResponse {
  lines: string[];
}

export interface SetupStatus {
  plex_configured: boolean;
  plex_url: string | null;
  plex_db_configured: boolean;
  radarr_configured: boolean;
  sonarr_configured: boolean;
}

export interface PlexAuthResponse {
  auth_url: string;
  pin_id: number;
}

export interface PlexCallbackResponse {
  success: boolean;
  message: string;
}

export interface ScanResult {
  status: string;
  sets_found: number;
  total_files: number;
  method: string;
}

export interface DeletionPreview {
  set_id: number;
  title: string;
  files_to_delete: Array<{ id: number; file_path: string; file_size: number }>;
  files_to_keep: Array<{ id: number; file_path: string; file_size: number }>;
  space_to_free: number;
}

// --- API modules ---

export const statsAPI = {
  getDashboardStats: () => fetchAPI<DashboardStats>("/api/stats/dashboard"),
  getHistory: (limit = 50, offset = 0) =>
    fetchAPI<HistoryResponse>(`/api/stats/history?limit=${limit}&offset=${offset}`),
};

export const scanAPI = {
  startScan: (libraryNames: string[], method: string) =>
    postAPI<ScanResult>("/api/scan/start", { library_names: libraryNames, method }),
  getStatus: () => fetchAPI<Record<string, number>>("/api/scan/status"),
  getDuplicates: (params?: { status?: string; media_type?: string; limit?: number; offset?: number }) => {
    const search = new URLSearchParams();
    if (params?.status) search.set("status", params.status);
    if (params?.media_type) search.set("media_type", params.media_type);
    if (params?.limit) search.set("limit", String(params.limit));
    if (params?.offset) search.set("offset", String(params.offset));
    const qs = search.toString();
    return fetchAPI<DuplicatesResponse>(`/api/scan/duplicates${qs ? `?${qs}` : ""}`);
  },
  previewDeletion: (setId: number) =>
    fetchAPI<DeletionPreview>(`/api/scan/duplicates/${setId}/preview`),
  deleteSet: (setId: number, dryRun: boolean) =>
    postAPI<Record<string, unknown>>(`/api/scan/duplicates/${setId}/delete`, { dry_run: dryRun }),
  updateFileKeep: (setId: number, fileId: number, keep: boolean) =>
    patchAPI<{ id: number; keep: boolean }>(`/api/scan/duplicates/${setId}/files/${fileId}`, { keep }),
};

export const configAPI = {
  getAll: () => fetchAPI<Record<string, string | null>>("/api/config"),
  update: (config: Record<string, string | null>) =>
    putAPI<{ status: string }>("/api/config", { config }),
  getLibraries: () => fetchAPI<PlexLibrary[]>("/api/config/libraries"),
};

export const setupAPI = {
  getStatus: () => fetchAPI<SetupStatus>("/api/setup/status"),
  getPlexAuthUrl: () => fetchAPI<PlexAuthResponse>("/api/setup/plex/auth-url"),
  checkPlexAuth: (pinId: number) =>
    postAPI<PlexCallbackResponse>("/api/setup/plex/callback", { pin_id: pinId }),
  testPlex: () => postAPI<{ success: boolean; message: string }>("/api/setup/plex/test"),
  getServers: (token: string) =>
    postAPI<Array<{ name: string; address: string }>>("/api/setup/plex/servers", { token }),
};

export const scoringAPI = {
  getRules: () => fetchAPI<ScoringRule[]>("/api/scoring/rules"),
  createRule: (rule: Omit<ScoringRule, "id" | "created_at">) =>
    postAPI<ScoringRule>("/api/scoring/rules", rule),
  updateRule: (id: number, rule: Partial<ScoringRule>) =>
    putAPI<ScoringRule>(`/api/scoring/rules/${id}`, rule),
    deleteRule: (id: number) => deleteAPI<{ status: string }>(`/api/scoring/rules/${id}`),
    scanFolderPriority: async (minCount: number) => {
        const res = await fetch(`/api/scoring/folder-priority/scan?min_count=${minCount}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
        });
        const text = await res.text();
        const data = text ? JSON.parse(text) : null;
        if (!res.ok) {
            throw new Error(data?.detail || "Folder scan failed");
        }
        return data as { folders: { path: string; file_count: number }[] };
    },

    listFolderPriority: async () => {
        const res = await fetch("/api/scoring/folder-priority", {
            method: "GET",
            headers: { "Content-Type": "application/json" },
        });
        const text = await res.text();
        const data = text ? JSON.parse(text) : null;
        if (!res.ok) {
            throw new Error(data?.detail || "Failed to load folder priorities");
        }
        return data as {
            id: number;
            path: string;
            priority: "high" | "medium" | "low";
            enabled: boolean;
        }[];
    },

    updateFolderPriority: async (
        id: number,
        body: Partial<{ priority: string; enabled: boolean }>
    ) => {
        const res = await fetch(`/api/scoring/folder-priority/${id}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        const text = await res.text();
        const data = text ? JSON.parse(text) : null;
        if (!res.ok) {
            throw new Error(data?.detail || "Failed to update folder priority");
        }
        return data;
    },
};

export const systemAPI = {
  getVersion: () => fetchAPI<VersionInfo>("/api/system/version"),
  getLogs: (lines = 100) => fetchAPI<LogsResponse>(`/api/system/logs?lines=${lines}`),
};
