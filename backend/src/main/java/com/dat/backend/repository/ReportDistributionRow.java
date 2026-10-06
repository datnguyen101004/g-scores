package com.dat.backend.repository;

import java.math.BigDecimal;

public interface ReportDistributionRow {

    BigDecimal getLowerBound();

    BigDecimal getUpperBound();

    Boolean getUpperInclusive();

    Long getCount();

    Long getTotalStudents();

    BigDecimal getAverageScore();

    BigDecimal getMedianScore();
}
