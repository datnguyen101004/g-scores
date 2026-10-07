package com.dat.backend.dto;

import java.math.BigDecimal;
import java.util.List;

import io.swagger.v3.oas.annotations.media.Schema;

public record ReportDistributionResponse(
        @Schema(description = "Subject included in the report", example = "toan") String subject,
        @Schema(description = "Number of students with a non-null score", minimum = "0", example = "1000000")
        long totalStudents,
        @Schema(description = "Arithmetic mean of non-null scores; null when there are no scores", nullable = true, example = "6.25")
        BigDecimal averageScore,
        @Schema(description = "Median of non-null scores; null when there are no scores", nullable = true, example = "6.5")
        BigDecimal medianScore,
        @Schema(description = "Ten ascending one-point buckets covering [0, 10]")
        List<ReportDistributionBin> bins) {
}
