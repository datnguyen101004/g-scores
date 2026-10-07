package com.dat.backend.repository;

import java.math.BigDecimal;

public interface StudentRankingProjection {

    int getRank();

    String getSbd();

    BigDecimal getScore1();

    BigDecimal getScore2();

    BigDecimal getScore3();

    BigDecimal getTotalScore();
}
