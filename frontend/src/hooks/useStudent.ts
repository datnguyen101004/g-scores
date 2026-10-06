import { useApiResource } from "./useApiResource";
import type { ApiResource, Student } from "../types/student";

export function useStudent(sbd: string | null): ApiResource<Student> {
  const url = sbd === null ? null : `/api/students/${encodeURIComponent(sbd)}`;
  return useApiResource<Student>(url);
}
