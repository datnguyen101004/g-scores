import type { ScoreSubject } from "@/components/scores/scoreColumns";

export interface ScoreDistributionBin {
  lowerBound: number;
  upperBound: number;
  upperInclusive: boolean;
  count: number;
}

export interface ScoreDistribution {
  subject: ScoreSubject;
  totalStudents: number;
  averageScore: number | null;
  medianScore: number | null;
  bins: ScoreDistributionBin[];
}
