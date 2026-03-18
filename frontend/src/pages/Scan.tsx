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
            prev.includes(title) ? prev.filter((l) => l !== title) : [...prev,
