package com.dat.backend.dto;

import java.math.BigDecimal;

import io.swagger.v3.oas.annotations.media.Schema;

public record ReportDistributionBin(
        @Schema(description = "Lower score bound, inclusive", example = "0.0") BigDecimal lowerBound,
        @Schema(description = "Upper score bound", example = "1.0") BigDecimal upperBound,
        @Schema(description = "Whether the upper bound is inclusive (true only for the final bucket)", example = "false")
        boolean upperInclusive,
        @Schema(description = "Number of students in this bucket", minimum = "0", example = "1234") long count) {
}
