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
      const poll = setInterval(async () =>
