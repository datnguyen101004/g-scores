package com.dat.backend.controller;

import com.dat.backend.dto.ApiErrorResponse;
import com.dat.backend.dto.StudentResponse;
import com.dat.backend.dto.TopStudentsResponse;
import com.dat.backend.dto.SuccessResponse;
import com.dat.backend.service.StudentService;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping(value = "/api/students", produces = MediaType.APPLICATION_JSON_VALUE)
@Tag(name = "Students", description = "Tra cứu điểm thi")
public class StudentController {

    private final StudentService studentService;

    public StudentController(StudentService studentService) {
        this.studentService = studentService;
    }

    @GetMapping("/{sbd}")
    @Operation(summary = "Tra cứu điểm theo số báo danh")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "Điểm của thí sinh", useReturnTypeSchema = true,
                    content = @Content(mediaType = "application/json")),
            @ApiResponse(responseCode = "404", description = "Không tìm thấy số báo danh",
                    content = @Content(mediaType = "application/json", schema = @Schema(implementation = ApiErrorResponse.class))),
            @ApiResponse(responseCode = "500", description = "Lỗi hệ thống",
                    content = @Content(mediaType = "application/json", schema = @Schema(implementation = ApiErrorResponse.class)))
    })
    public SuccessResponse<StudentResponse> getStudentBySbd(
            @Parameter(description = "Nhập đầy đủ số báo danh, kể cả số 0 ở đầu", example = "01000001", schema = @Schema(type = "string"))
            @PathVariable("sbd") String sbd) {
        return new SuccessResponse<>(200, studentService.getStudentBySbd(sbd));
    }

    @GetMapping("/top-10")
    @Operation(summary = "Top 10 thí sinh khối A (Toán, Vật lí, Hóa học)")
    @ApiResponses({
            @ApiResponse(responseCode = "200", description = "10 vị trí đầu kèm tất cả thí sinh đồng hạng ở vị trí thứ 10",
                    useReturnTypeSchema = true, content = @Content(mediaType = "application/json")),
            @ApiResponse(responseCode = "500", description = "Lỗi hệ thống",
                    content = @Content(mediaType = "application/json", schema = @Schema(implementation = ApiErrorResponse.class)))
    })
    public SuccessResponse<TopStudentsResponse> getTopStudents() {
        return new SuccessResponse<>(200, studentService.getTopStudents());
    }
}
