package com.dat.backend.service;

import com.dat.backend.dto.StudentResponse;
import com.dat.backend.dto.TopStudentsResponse;

public interface StudentService {

    StudentResponse getStudentBySbd(String sbd);

    TopStudentsResponse getTopStudents();
}
