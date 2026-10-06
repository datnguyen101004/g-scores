package com.dat.backend.dto;

public record SuccessResponse<T>(int statusCode, T data) {
}
