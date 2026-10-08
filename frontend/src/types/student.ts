export interface Student {
  sbd: string;
  toan: number | null;
  nguVan: number | null;
  ngoaiNgu: number | null;
  vatLi: number | null;
  hoaHoc: number | null;
  sinhHoc: number | null;
  lichSu: number | null;
  diaLi: number | null;
  gdcd: number | null;
  maNgoaiNgu: string | null;
}

export interface RankedStudent {
  rank: number;
  sbd: string;
  scores: { toan: number; vatLi: number; hoaHoc: number };
  totalScore: number;
}

export interface TopStudents {
  group: "A";
  subjects: ("toan" | "vatLi" | "hoaHoc")[];
  students: RankedStudent[];
}

export interface ApiError {
  kind: "http" | "network" | "timeout";
  statusCode: number | null;
  message: string;
  timestamp?: string;
  path?: string;
}

export interface ApiResource<T> {
  data: T | null;
  loading: boolean;
  error: ApiError | null;
  refetch: () => void;
}
