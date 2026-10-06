package com.dat.backend.exception;

import java.time.Instant;

import com.dat.backend.dto.ApiErrorResponse;
import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class GlobalExceptionHandler {

    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(StudentNotFoundException.class)
    public ResponseEntity<Object> handleStudentNotFound(StudentNotFoundException exception, HttpServletRequest request) {
        return errorResponse(exception, exception.getMessage(), HttpStatus.NOT_FOUND, request);
    }

    @ExceptionHandler(InvalidReportRequestException.class)
    public ResponseEntity<Object> handleInvalidReportRequest(
            InvalidReportRequestException exception, HttpServletRequest request) {
        return errorResponse(exception, exception.getMessage(), HttpStatus.BAD_REQUEST, request);
    }

    private ResponseEntity<Object> errorResponse(
            Exception exception, String message, HttpStatus status, HttpServletRequest request) {
        String path = request.getRequestURI();
        if (status.is5xxServerError()) {
            log.error("API request failed: status={}, path={}", status.value(), path, exception);
        } else {
            log.warn("API request failed: status={}, path={}, message={}", status.value(), path, message);
        }
        return ResponseEntity.status(status).contentType(MediaType.APPLICATION_JSON)
                .body(new ApiErrorResponse(status.value(), message, Instant.now(), path));
    }

    @ExceptionHandler(Exception.class)
    public ResponseEntity<Object> handleUnexpectedException(Exception exception, HttpServletRequest request) {
        return errorResponse(exception, "Đã xảy ra lỗi hệ thống. Vui lòng thử lại sau.",
                HttpStatus.INTERNAL_SERVER_ERROR, request);
    }
}
