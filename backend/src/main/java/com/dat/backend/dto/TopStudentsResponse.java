package com.dat.backend.dto;

import java.util.List;

import io.swagger.v3.oas.annotations.media.Schema;

public record TopStudentsResponse(
        @Schema(description = "Khối A: Toán, Vật lí, Hóa học", allowableValues = {"A"}, example = "A")
        String group,
        @Schema(description = "Các khóa điểm có mặt trong scores, theo thứ tự môn của tổ hợp",
                example = "[\"toan\",\"vatLi\",\"hoaHoc\"]")
        List<String> subjects,
        @Schema(description = "10 vị trí đầu và tất cả thí sinh đồng tổng điểm và điểm môn cao nhất ở vị trí thứ 10; có thể hơn 10 người.")
        List<RankedStudentResponse> students) {
}
