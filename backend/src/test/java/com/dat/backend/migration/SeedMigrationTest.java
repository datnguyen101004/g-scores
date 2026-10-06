package com.dat.backend.migration;

import org.flywaydb.core.Flyway;
import org.flywaydb.core.api.FlywayException;
import org.flywaydb.core.api.MigrationInfo;
import org.flywaydb.core.api.output.MigrateResult;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;

import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.UUID;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Testcontainers
class SeedMigrationTest {

    private static final String HEADER = "sbd,toan,ngu_van,ngoai_ngu,vat_li,hoa_hoc,sinh_hoc,lich_su,dia_li,gdcd,ma_ngoai_ngu";
    private static final String SCORE_COLUMNS = "toan, ngu_van, ngoai_ngu, vat_li, hoa_hoc, sinh_hoc, lich_su, dia_li, gdcd";

    @Container
    private static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer("postgres:17-alpine");

    @TempDir
    Path tempDir;

    @Test
    void successfulSeedPreservesValuesAndSkipsOnTheNextMigration() throws Exception {
        String schema = newSchema();
        Path csv = writeCsv(
                HEADER,
                csvRow("00001234", "9.25", "8.50", "", "7.00", "", "", "", "", "", "N1"),
                csvRow("00000007", "", "6.75", "9.00", "", "", "", "", "", "", "N7"));
        Flyway flyway = flyway(csv, schema);

        MigrateResult firstRun = flyway.migrate();

        assertEquals(2, firstRun.migrationsExecuted);
        assertEquals(List.of(
                score("00000007", null, "6.75", "9.00", null, null, null, null, null, null, "N7"),
                score("00001234", "9.25", "8.50", null, "7.00", null, null, null, null, null, "N1")),
                readScores(schema));
        assertEquals(List.of(new MigrationRecord("1", true), new MigrationRecord("2", true)),
                readHistory(schema));

        Files.delete(csv);
        updateToan(schema, "00001234", new BigDecimal("3.33"));
        MigrateResult secondRun = flyway.migrate();

        assertEquals(0, secondRun.migrationsExecuted);
        assertEquals(List.of(
                score("00000007", null, "6.75", "9.00", null, null, null, null, null, null, "N7"),
                score("00001234", "3.33", "8.50", null, "7.00", null, null, null, null, null, "N1")),
                readScores(schema));
        assertEquals(List.of(new MigrationRecord("1", true), new MigrationRecord("2", true)),
                readHistory(schema));
    }

    @Test
    void failedCopyRollsBackAndRetriesOnTheNextMigration() throws Exception {
        String schema = newSchema();
        Path csv = writeCsv(
                HEADER,
                csvRow("00000200", "1.25", "2.50", "", "", "", "", "", "", "", "N2"),
                csvRow("00000201", "not-a-number", "3.50", "", "", "", "", "", "", "", "N3"));
        Flyway flyway = flyway(csv, schema);

        assertThrows(FlywayException.class, flyway::migrate);

        assertEquals(0, countScores(schema));
        assertEquals(List.of(new MigrationRecord("1", true)), readHistory(schema));
        assertVersionTwoPending(flyway);

        writeCsv(csv,
                HEADER,
                csvRow("00000200", "1.25", "2.50", "", "", "", "", "", "", "", "N2"),
                csvRow("00000201", "4.75", "3.50", "", "", "", "", "", "", "", "N3"));
        MigrateResult retry = flyway.migrate();

        assertEquals(1, retry.migrationsExecuted);
        assertEquals(List.of(
                score("00000200", "1.25", "2.50", null, null, null, null, null, null, null, "N2"),
                score("00000201", "4.75", "3.50", null, null, null, null, null, null, null, "N3")),
                readScores(schema));
        assertEquals(List.of(new MigrationRecord("1", true), new MigrationRecord("2", true)),
                readHistory(schema));
    }

    @Test
    void reorderedHeaderFailsInsteadOfChangingSubjectAssignments() throws Exception {
        String schema = newSchema();
        Path csv = writeCsv(
                "sbd,ngu_van,toan,ngoai_ngu,vat_li,hoa_hoc,sinh_hoc,lich_su,dia_li,gdcd,ma_ngoai_ngu",
                csvRow("00000300", "8.50", "9.25", "", "", "", "", "", "", "", "N4"));
        Flyway flyway = flyway(csv, schema);

        assertThrows(FlywayException.class, flyway::migrate);

        assertEquals(0, countScores(schema));
        assertEquals(List.of(new MigrationRecord("1", true)), readHistory(schema));
        assertVersionTwoPending(flyway);
    }

    @Test
    void emptyAndHeaderOnlyCsvFilesCannotCompleteTheSeed() throws Exception {
        for (String contents : List.of("", HEADER + System.lineSeparator())) {
            String schema = newSchema();
            Path csv = tempDir.resolve("seed-" + UUID.randomUUID() + ".csv");
            Files.writeString(csv, contents, StandardCharsets.UTF_8);
            Flyway flyway = flyway(csv, schema);

            assertThrows(FlywayException.class, flyway::migrate);

            assertEquals(0, countScores(schema));
            assertEquals(List.of(new MigrationRecord("1", true)), readHistory(schema));
            assertVersionTwoPending(flyway);
        }
    }

    private Flyway flyway(Path csv, String schema) {
        return Flyway.configure()
                .dataSource(POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword())
                .schemas(schema)
                .defaultSchema(schema)
                .locations("classpath:db/migration")
                .javaMigrations(new V2__Seed_exam_scores(csv.toString()))
                .load();
    }

    private Path writeCsv(String... lines) throws Exception {
        Path csv = tempDir.resolve("seed-" + UUID.randomUUID() + ".csv");
        writeCsv(csv, lines);
        return csv;
    }

    private static void writeCsv(Path csv, String... lines) throws Exception {
        Files.writeString(csv, String.join(System.lineSeparator(), lines) + System.lineSeparator(),
                StandardCharsets.UTF_8);
    }

    private static String csvRow(String... fields) {
        return String.join(",", fields);
    }

    private static String newSchema() {
        return "seed_test_" + UUID.randomUUID().toString().replace("-", "");
    }

    private static Connection connect() throws SQLException {
        return DriverManager.getConnection(POSTGRES.getJdbcUrl(), POSTGRES.getUsername(), POSTGRES.getPassword());
    }

    private static String table(String schema, String tableName) {
        return "\"" + schema + "\".\"" + tableName + "\"";
    }

    private static long countScores(String schema) throws SQLException {
        try (Connection connection = connect();
             Statement statement = connection.createStatement();
             ResultSet result = statement.executeQuery("SELECT count(*) FROM " + table(schema, "exam_scores"))) {
            result.next();
            return result.getLong(1);
        }
    }

    private static List<Score> readScores(String schema) throws SQLException {
        String sql = "SELECT sbd, " + SCORE_COLUMNS + ", ma_ngoai_ngu FROM " + table(schema, "exam_scores")
                + " ORDER BY sbd";
        List<Score> rows = new ArrayList<>();
        try (Connection connection = connect();
             Statement statement = connection.createStatement();
             ResultSet result = statement.executeQuery(sql)) {
            while (result.next()) {
                rows.add(new Score(
                        result.getString("sbd"),
                        Arrays.asList(
                                result.getBigDecimal("toan"),
                                result.getBigDecimal("ngu_van"),
                                result.getBigDecimal("ngoai_ngu"),
                                result.getBigDecimal("vat_li"),
                                result.getBigDecimal("hoa_hoc"),
                                result.getBigDecimal("sinh_hoc"),
                                result.getBigDecimal("lich_su"),
                                result.getBigDecimal("dia_li"),
                                result.getBigDecimal("gdcd")),
                        result.getString("ma_ngoai_ngu")));
            }
        }
        return rows;
    }

    private static void updateToan(String schema, String sbd, BigDecimal value) throws SQLException {
        try (Connection connection = connect();
             PreparedStatement statement = connection.prepareStatement(
                     "UPDATE " + table(schema, "exam_scores") + " SET toan = ? WHERE sbd = ?")) {
            statement.setBigDecimal(1, value);
            statement.setString(2, sbd);
            assertEquals(1, statement.executeUpdate());
        }
    }

    private static List<MigrationRecord> readHistory(String schema) throws SQLException {
        List<MigrationRecord> records = new ArrayList<>();
        try (Connection connection = connect();
             Statement statement = connection.createStatement();
             ResultSet result = statement.executeQuery(
                     "SELECT version, success FROM " + table(schema, "flyway_schema_history")
                             + " WHERE version IS NOT NULL ORDER BY installed_rank")) {
            while (result.next()) {
                records.add(new MigrationRecord(result.getString("version"), result.getBoolean("success")));
            }
        }
        return records;
    }

    private static void assertVersionTwoPending(Flyway flyway) {
        assertTrue(Arrays.stream(flyway.info().pending())
                .map(MigrationInfo::getVersion)
                .anyMatch(version -> version != null && "2".equals(version.getVersion())));
        assertFalse(Arrays.stream(flyway.info().applied())
                .filter(migration -> migration.getVersion() != null)
                .anyMatch(migration -> "2".equals(migration.getVersion().getVersion())));
    }

    private static Score score(String sbd, String toan, String nguVan, String ngoaiNgu, String vatLi,
                              String hoaHoc, String sinhHoc, String lichSu, String diaLi, String gdcd,
                              String languageCode) {
        return new Score(sbd, Arrays.asList(
                decimal(toan), decimal(nguVan), decimal(ngoaiNgu), decimal(vatLi), decimal(hoaHoc),
                decimal(sinhHoc), decimal(lichSu), decimal(diaLi), decimal(gdcd)), languageCode);
    }

    private static BigDecimal decimal(String value) {
        return value == null ? null : new BigDecimal(value);
    }

    private record Score(String sbd, List<BigDecimal> subjects, String languageCode) {
    }

    private record MigrationRecord(String version, boolean success) {
    }
}
