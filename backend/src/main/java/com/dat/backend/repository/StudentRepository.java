package com.dat.backend.repository;

import java.util.List;

import com.dat.backend.entity.Student;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;

public interface StudentRepository extends JpaRepository<Student, String> {

    @Query(value = """
            SELECT sbd, score1, score2, score3, "totalScore",
                   RANK() OVER (ORDER BY "totalScore" DESC, highest_score DESC) AS rank
            FROM (
                SELECT sbd, toan AS score1, vat_li AS score2, hoa_hoc AS score3,
                       toan + vat_li + hoa_hoc AS "totalScore",
                       GREATEST(toan, vat_li, hoa_hoc) AS highest_score
                FROM exam_scores
                WHERE toan IS NOT NULL AND vat_li IS NOT NULL AND hoa_hoc IS NOT NULL
                ORDER BY "totalScore" DESC, highest_score DESC
                FETCH FIRST 10 ROWS WITH TIES
            ) ranked
            ORDER BY "totalScore" DESC, highest_score DESC, sbd ASC
            """, nativeQuery = true)
    List<StudentRankingProjection> findTopStudents();
}
