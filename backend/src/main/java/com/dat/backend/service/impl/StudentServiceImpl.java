package com.dat.backend.service.impl;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import com.dat.backend.dto.RankedStudentResponse;
import com.dat.backend.dto.StudentResponse;
import com.dat.backend.dto.TopStudentsResponse;
import com.dat.backend.exception.StudentNotFoundException;
import com.dat.backend.repository.StudentRepository;
import com.dat.backend.repository.StudentRankingProjection;
import com.dat.backend.service.StudentService;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class StudentServiceImpl implements StudentService {

    private static final List<String> GROUP_A_SUBJECTS = List.of("toan", "vatLi", "hoaHoc");

    private final StudentRepository studentRepository;

    public StudentServiceImpl(StudentRepository studentRepository) {
        this.studentRepository = studentRepository;
    }

    @Override
    public StudentResponse getStudentBySbd(String sbd) {
        return studentRepository.findById(sbd)
                .map(StudentResponse::from)
                .orElseThrow(StudentNotFoundException::new);
    }

    @Override
    public TopStudentsResponse getTopStudents() {
        List<StudentRankingProjection> rows = studentRepository.findTopStudents();
        List<RankedStudentResponse> students = new ArrayList<>(rows.size());
        for (StudentRankingProjection row : rows) {
            Map<String, BigDecimal> scores = new LinkedHashMap<>(4);
            scores.put("toan", row.getScore1());
            scores.put("vatLi", row.getScore2());
            scores.put("hoaHoc", row.getScore3());
            students.add(new RankedStudentResponse(
                    row.getRank(), row.getSbd(), scores, row.getTotalScore()));
        }
        return new TopStudentsResponse("A", GROUP_A_SUBJECTS, students);
    }
}
