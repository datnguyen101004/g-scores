package com.dat.backend.exception;

public class StudentNotFoundException extends RuntimeException {

    public StudentNotFoundException() {
        super("Không tìm thấy số báo danh.");
    }
}
