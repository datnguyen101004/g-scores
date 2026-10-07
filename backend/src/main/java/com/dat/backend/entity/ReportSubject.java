package com.dat.backend.entity;

import java.util.Optional;

public enum ReportSubject {
    TOAN("toan", "toan"),
    NGU_VAN("nguVan", "nguVan"),
    NGOAI_NGU("ngoaiNgu", "ngoaiNgu"),
    VAT_LI("vatLi", "vatLi"),
    HOA_HOC("hoaHoc", "hoaHoc"),
    SINH_HOC("sinhHoc", "sinhHoc"),
    LICH_SU("lichSu", "lichSu"),
    DIA_LI("diaLi", "diaLi"),
    GDCD("gdcd", "gdcd");

    private static final ReportSubject[] SUBJECTS = values();

    private final String apiKey;
    private final String entityAttribute;

    ReportSubject(String apiKey, String entityAttribute) {
        this.apiKey = apiKey;
        this.entityAttribute = entityAttribute;
    }

    public static Optional<ReportSubject> findByApiKey(String apiKey) {
        if (apiKey == null) {
            return Optional.empty();
        }
        for (ReportSubject subject : SUBJECTS) {
            if (subject.apiKey.equals(apiKey)) {
                return Optional.of(subject);
            }
        }
        return Optional.empty();
    }

    public String getApiKey() {
        return apiKey;
    }

    public String getEntityAttribute() {
        return entityAttribute;
    }
}
