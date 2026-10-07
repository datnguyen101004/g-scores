package com.dat.backend.dto;

import java.math.BigDecimal;
import java.util.Map;

import io.swagger.v3.oas.annotations.media.Schema;

public record RankedStudentResponse(
        @Schema(description = "Cùng tổng điểm và điểm môn cao nhất thì cùng hạng; hạng tiếp theo bỏ qua số người đồng hạng (1, 2, 2, 4)", example = "1") int rank,
        @Schema(description = "Số báo danh", example = "01000001") String sbd,
        @Schema(description = "Điểm theo từng môn trong tổ hợp", example = "{\"toan\":9.5,\"vatLi\":9.0,\"hoaHoc\":8.5}")
        Map<String, BigDecimal> scores,
        @Schema(description = "Tổng điểm ba môn", example = "27.00") BigDecimal totalScore) {
}
