package com.dat.backend.dto;

import java.math.BigDecimal;

import com.dat.backend.entity.Student;
import io.swagger.v3.oas.annotations.media.Schema;

public record StudentResponse(
        @Schema(description = "Số báo danh", example = "01000001") String sbd,
        @Schema(description = "Toán", nullable = true) BigDecimal toan,
        @Schema(description = "Ngữ văn", nullable = true) BigDecimal nguVan,
        @Schema(description = "Ngoại ngữ", nullable = true) BigDecimal ngoaiNgu,
        @Schema(description = "Vật lí", nullable = true) BigDecimal vatLi,
        @Schema(description = "Hóa học", nullable = true) BigDecimal hoaHoc,
        @Schema(description = "Sinh học", nullable = true) BigDecimal sinhHoc,
        @Schema(description = "Lịch sử", nullable = true) BigDecimal lichSu,
        @Schema(description = "Địa lí", nullable = true) BigDecimal diaLi,
        @Schema(description = "Giáo dục công dân", nullable = true) BigDecimal gdcd,
        @Schema(description = "Mã ngoại ngữ", nullable = true) String maNgoaiNgu) {

    public static StudentResponse from(Student student) {
        return new StudentResponse(
                student.getSbd(), student.getToan(), student.getNguVan(), student.getNgoaiNgu(),
                student.getVatLi(), student.getHoaHoc(), student.getSinhHoc(), student.getLichSu(),
                student.getDiaLi(), student.getGdcd(), student.getMaNgoaiNgu());
    }
}
