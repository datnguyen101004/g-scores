package com.dat.backend.service;

import com.dat.backend.dto.ReportCountResponse;
import com.dat.backend.dto.ReportDistributionResponse;

public interface ReportService {

    ReportCountResponse countStudents(String subject, String scoreBand);

    ReportDistributionResponse getScoreDistribution(String subject);
}
