package com.dat.backend.migration;

import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;

import org.flywaydb.core.api.migration.BaseJavaMigration;
import org.flywaydb.core.api.migration.Context;
import org.postgresql.PGConnection;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class V2__Seed_exam_scores extends BaseJavaMigration {

    private static final String COPY_SQL = "COPY exam_scores (sbd, toan, ngu_van, ngoai_ngu, "
            + "vat_li, hoa_hoc, sinh_hoc, lich_su, dia_li, gdcd, ma_ngoai_ngu) "
            + "FROM STDIN WITH (FORMAT CSV, HEADER MATCH, ENCODING 'UTF8')";

    private final Path csvPath;

    public V2__Seed_exam_scores(@Value("${app.seed.csv-path}") String csvPath) {
        this.csvPath = Path.of(csvPath);
    }

    @Override
    public void migrate(Context context) throws Exception {
        long copiedRows;
        try (InputStream input = Files.newInputStream(csvPath)) {
            PGConnection connection = context.getConnection().unwrap(PGConnection.class);
            copiedRows = connection.getCopyAPI().copyIn(COPY_SQL, input);
        }

        if (copiedRows == 0) {
            throw new IllegalStateException("CSV seed file contains no data rows: " + csvPath);
        }
    }
}
