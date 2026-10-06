package com.dat.backend.service;

import java.math.BigDecimal;

public enum ScoreBand {
    GTE_8(new BigDecimal("8"), null),
    FROM_6_TO_8(new BigDecimal("6"), new BigDecimal("8")),
    FROM_4_TO_6(new BigDecimal("4"), new BigDecimal("6")),
    LT_4(null, new BigDecimal("4"));

    private final BigDecimal lowerBound;
    private final BigDecimal upperBound;

    ScoreBand(BigDecimal lowerBound, BigDecimal upperBound) {
        this.lowerBound = lowerBound;
        this.upperBound = upperBound;
    }

    public BigDecimal getLowerBound() {
        return lowerBound;
    }

    public BigDecimal getUpperBound() {
        return upperBound;
    }
}
