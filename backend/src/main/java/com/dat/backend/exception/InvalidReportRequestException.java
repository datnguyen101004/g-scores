package com.dat.backend.exception;

public class InvalidReportRequestException extends RuntimeException {

    public InvalidReportRequestException(String message) {
        super(message);
    }
}
