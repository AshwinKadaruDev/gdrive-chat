import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  getProjects,
  createProject,
  deleteProject,
  triggerSync,
  getSyncStatus,
  validateFolder,
} from "@/services/api";

export function useProjects() {
  return useQuery({
    queryKey: ["projects"],
    queryFn: getProjects,
  });
}

export function useProjectSyncStatus(projectId: string | null) {
  return useQuery({
    queryKey: ["project-sync", projectId],
    queryFn: () => getSyncStatus(projectId!),
    enabled: !!projectId,
    refetchInterval: (query) => {
      const status = query.state.data?.sync_status;
      if (status === "SYNCING") {
        return 3000;
      }
      return false;
    },
  });
}

export function useValidateFolder() {
  return useMutation({
    mutationFn: (gdrive_folder_url: string) =>
      validateFolder(gdrive_folder_url),
  });
}

export function useCreateProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      gdrive_folder_url,
      name,
    }: {
      gdrive_folder_url: string;
      name?: string;
    }) => createProject(gdrive_folder_url, name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export function useDeleteProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) => deleteProject(projectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}

export function useSyncProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (projectId: string) => triggerSync(projectId),
    onSuccess: (_data, projectId) => {
      queryClient.invalidateQueries({ queryKey: ["projects"] });
      queryClient.invalidateQueries({
        queryKey: ["project-sync", projectId],
      });
    },
  });
}
