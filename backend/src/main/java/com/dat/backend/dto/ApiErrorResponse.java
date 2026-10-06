package com.dat.backend.dto;

import java.time.Instant;

public record ApiErrorResponse(int statusCode, String message, Instant timestamp, String path) {
}
