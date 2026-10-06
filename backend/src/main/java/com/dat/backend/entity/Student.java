package com.dat.backend.entity;

import java.math.BigDecimal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

@Entity
@Table(name = "exam_scores")
@Getter
@Setter
@NoArgsConstructor
public class Student {

    @Id
    @Column(name = "sbd", nullable = false, length = 8)
    private String sbd;

    @Column(name = "toan", precision = 4, scale = 2)
    private BigDecimal toan;

    @Column(name = "ngu_van", precision = 4, scale = 2)
    private BigDecimal nguVan;

    @Column(name = "ngoai_ngu", precision = 4, scale = 2)
    private BigDecimal ngoaiNgu;

    @Column(name = "vat_li", precision = 4, scale = 2)
    private BigDecimal vatLi;

    @Column(name = "hoa_hoc", precision = 4, scale = 2)
    private BigDecimal hoaHoc;

    @Column(name = "sinh_hoc", precision = 4, scale = 2)
    private BigDecimal sinhHoc;

    @Column(name = "lich_su", precision = 4, scale = 2)
    private BigDecimal lichSu;

    @Column(name = "dia_li", precision = 4, scale = 2)
    private BigDecimal diaLi;

    @Column(name = "gdcd", precision = 4, scale = 2)
    private BigDecimal gdcd;

    @Column(name = "ma_ngoai_ngu", length = 2)
    private String maNgoaiNgu;
}