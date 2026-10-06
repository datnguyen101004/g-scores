package com.dat.backend.repository;

import java.util.List;

import com.dat.backend.entity.Student;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface ReportRepository extends JpaRepository<Student, String>, JpaSpecificationExecutor<Student> {

    @Query(value = """
            WITH selected_scores AS (
                SELECT CASE :subject
                    WHEN 'toan' THEN toan
                    WHEN 'nguVan' THEN ngu_van
                    WHEN 'ngoaiNgu' THEN ngoai_ngu
                    WHEN 'vatLi' THEN vat_li
                    WHEN 'hoaHoc' THEN hoa_hoc
                    WHEN 'sinhHoc' THEN sinh_hoc
                    WHEN 'lichSu' THEN lich_su
                    WHEN 'diaLi' THEN dia_li
                    WHEN 'gdcd' THEN gdcd
                    ELSE NULL::numeric
                END AS score
                FROM exam_scores
            ),
            valid_scores AS MATERIALIZED (
                SELECT score
                FROM selected_scores
                WHERE score IS NOT NULL
            ),
            score_summary AS (
                SELECT
                    COUNT(*)::bigint AS total_students,
                    AVG(score) AS average_score,
                    (
                        SELECT AVG(score)
                        FROM (
                            SELECT
                                score,
                                ROW_NUMBER() OVER (ORDER BY score) AS score_position,
                                COUNT(*) OVER () AS score_count
                            FROM valid_scores
                        ) ordered_scores
                        WHERE score_position IN ((score_count + 1) / 2, (score_count + 2) / 2)
                    ) AS median_score
                FROM valid_scores
            ),
            histogram AS (
                SELECT
                    LEAST(FLOOR(score), 9)::integer AS bucket_index,
                    COUNT(*)::bigint AS bucket_count
                FROM valid_scores
                GROUP BY 1
            )
            SELECT
                bucket_index::numeric AS "lowerBound",
                (bucket_index + 1)::numeric AS "upperBound",
                (bucket_index = 9) AS "upperInclusive",
                COALESCE(histogram.bucket_count, 0)::bigint AS "count",
                score_summary.total_students AS "totalStudents",
                score_summary.average_score AS "averageScore",
                score_summary.median_score AS "medianScore"
            FROM generate_series(0, 9) AS buckets(bucket_index)
            CROSS JOIN score_summary
            LEFT JOIN histogram USING (bucket_index)
            ORDER BY bucket_index
            """, nativeQuery = true)
    List<ReportDistributionRow> findScoreDistribution(@Param("subject") String subject);
}
