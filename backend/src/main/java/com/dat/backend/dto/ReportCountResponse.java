package com.dat.backend.dto;

import io.swagger.v3.oas.annotations.media.Schema;

public record ReportCountResponse(
        @Schema(description = "Môn học được thống kê", example = "toan") String subject,
        @Schema(description = "Mức điểm được thống kê", example = "GTE_8") String scoreBand,
        @Schema(description = "Số thí sinh có điểm phù hợp", minimum = "0", format = "int64", example = "198392") long count) {
}
