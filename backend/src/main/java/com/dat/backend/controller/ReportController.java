package com.dat.backend.controller;

import com.dat.backend.dto.ApiErrorResponse;
import com.dat.backend.dto.ReportCountResponse;
import com.dat.backend.dto.ReportDistributionResponse;
import com.dat.backend.dto.SuccessResponse;
import com.dat.backend.service.ReportService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping(value = "/api/reports", produces = MediaType.APPLICATION_JSON_VALUE)
@Tag(name = "Reports", description = "Báo cáo thí sinh theo môn và khoảng điểm")
public class ReportController {

    private final ReportService reportService;

    public ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/students")
    @Operation(summary = "Thống kê số thí sinh theo môn và khoảng điểm",
            description = "Chỉ đếm điểm khác null. GTE_8: điểm >= 8; FROM_6_TO_8: 6 <= điểm < 8; "
                    + "FROM_4_TO_6: 4 <= điểm < 6; LT_4: điểm < 4. Không trả chi tiết thí sinh hoặc phân trang.")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Số thí sinh phù hợp với môn và khoảng điểm",
                    useReturnTypeSchema = true, content = @Content(mediaType = "application/json")),
            @ApiResponse(responseCode = "400", description = "Tham số báo cáo không hợp lệ",
                    content = @Content(mediaType = "application/json",
                            schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "500", description = "Lỗi hệ thống",
                    content = @Content(mediaType = "application/json",
                            schema = @Schema(implementation = ApiErrorResponse.class)))
    })
    public SuccessResponse<ReportCountResponse> countStudents(
            @Parameter(description = "Môn cần lọc (bắt buộc)", required = true, example = "toan",
                    schema = @Schema(type = "string", allowableValues = {
                            "toan", "nguVan", "ngoaiNgu", "vatLi", "hoaHoc", "sinhHoc", "lichSu", "diaLi", "gdcd"
                    }))
            @RequestParam(name = "subject", defaultValue = "") String subject,
            @Parameter(description = "Khoảng điểm (bắt buộc): GTE_8 >= 8; FROM_6_TO_8 [6,8); "
                    + "FROM_4_TO_6 [4,6); LT_4 < 4", required = true, example = "GTE_8",
                    schema = @Schema(type = "string", allowableValues = {
                            "GTE_8", "FROM_6_TO_8", "FROM_4_TO_6", "LT_4"
                    }))
            @RequestParam(name = "scoreBand", defaultValue = "") String scoreBand) {
        return new SuccessResponse<>(200, reportService.countStudents(subject, scoreBand));
    }

    @GetMapping("/distribution")
    @Operation(summary = "Phổ điểm và thống kê điểm trung bình theo môn",
            description = "Trả về số thí sinh có điểm, trung bình, trung vị và 10 khoảng điểm rộng 1. "
                    + "Điểm null bị loại; điểm 10 thuộc khoảng cuối [9, 10].")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Phổ điểm của môn được chọn",
                    useReturnTypeSchema = true, content = @Content(mediaType = "application/json")),
            @ApiResponse(responseCode = "400", description = "Môn học không hợp lệ",
                    content = @Content(mediaType = "application/json",
                            schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "500", description = "Lỗi hệ thống",
                    content = @Content(mediaType = "application/json",
                            schema = @Schema(implementation = ApiErrorResponse.class)))
    })
    public SuccessResponse<ReportDistributionResponse> getScoreDistribution(
            @Parameter(description = "Môn cần thống kê (bắt buộc)", required = true, example = "toan",
                    schema = @Schema(type = "string", allowableValues = {
                            "toan", "nguVan", "ngoaiNgu", "vatLi", "hoaHoc", "sinhHoc", "lichSu", "diaLi", "gdcd"
                    }))
            @RequestParam(name = "subject", defaultValue = "") String subject) {
        return new SuccessResponse<>(200, reportService.getScoreDistribution(subject));
    }
}
