package com.dat.backend.service.impl;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;

import com.dat.backend.dto.ReportCountResponse;
import com.dat.backend.dto.ReportDistributionBin;
import com.dat.backend.dto.ReportDistributionResponse;
import com.dat.backend.entity.ReportSubject;
import com.dat.backend.entity.Student;
import com.dat.backend.exception.InvalidReportRequestException;
import com.dat.backend.repository.ReportDistributionRow;
import com.dat.backend.repository.ReportRepository;
import com.dat.backend.service.ReportService;
import com.dat.backend.service.ScoreBand;
import jakarta.persistence.criteria.Path;
import jakarta.persistence.criteria.Predicate;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class ReportServiceImpl implements ReportService {

    private static final String SUBJECT_ERROR =
            "Tham số subject là bắt buộc và phải là một trong: toan, nguVan, ngoaiNgu, vatLi, hoaHoc, sinhHoc, lichSu, diaLi, gdcd.";
    private static final String SCORE_BAND_ERROR =
            "Tham số scoreBand là bắt buộc và phải là một trong: GTE_8, FROM_6_TO_8, FROM_4_TO_6, LT_4.";

    private final ReportRepository reportRepository;

    public ReportServiceImpl(ReportRepository reportRepository) {
        this.reportRepository = reportRepository;
    }

    @Override
    @Cacheable(cacheNames = "scoreCounts", key = "#p0 + ':' + #p1")
    public ReportCountResponse countStudents(String subjectCode, String scoreBandCode) {
        ReportSubject subject = ReportSubject.findByApiKey(subjectCode)
                .orElseThrow(() -> new InvalidReportRequestException(SUBJECT_ERROR));
        ScoreBand scoreBand = findScoreBand(scoreBandCode);

        Specification<Student> scoreFilter = (root, query, criteriaBuilder) -> {
            Path<BigDecimal> score = root.<BigDecimal>get(subject.getEntityAttribute());
            Predicate predicate = criteriaBuilder.isNotNull(score);
            BigDecimal lowerBound = scoreBand.getLowerBound();
            if (lowerBound != null) {
                predicate = criteriaBuilder.and(predicate, criteriaBuilder.greaterThanOrEqualTo(score, lowerBound));
            }
            BigDecimal upperBound = scoreBand.getUpperBound();
            if (upperBound != null) {
                predicate = criteriaBuilder.and(predicate, criteriaBuilder.lessThan(score, upperBound));
            }
            return predicate;
        };
        long count = reportRepository.count(scoreFilter);
        return new ReportCountResponse(subject.getApiKey(), scoreBand.name(), count);
    }

    @Override
    @Cacheable(cacheNames = "scoreDistributions", key = "#p0")
    public ReportDistributionResponse getScoreDistribution(String subjectCode) {
        ReportSubject subject = ReportSubject.findByApiKey(subjectCode)
                .orElseThrow(() -> new InvalidReportRequestException(SUBJECT_ERROR));

        List<ReportDistributionRow> rows = reportRepository.findScoreDistribution(subject.getApiKey());
        ReportDistributionRow summary = rows.get(0);
        List<ReportDistributionBin> bins = new ArrayList<>(rows.size());
        for (ReportDistributionRow row : rows) {
            bins.add(new ReportDistributionBin(
                    row.getLowerBound(),
                    row.getUpperBound(),
                    row.getUpperInclusive(),
                    row.getCount()));
        }
        return new ReportDistributionResponse(
                subject.getApiKey(),
                summary.getTotalStudents(),
                summary.getAverageScore(),
                summary.getMedianScore(),
                bins);
    }

    private ScoreBand findScoreBand(String scoreBandCode) {
        try {
            return ScoreBand.valueOf(scoreBandCode);
        } catch (IllegalArgumentException | NullPointerException exception) {
            throw new InvalidReportRequestException(SCORE_BAND_ERROR);
        }
    }

}
