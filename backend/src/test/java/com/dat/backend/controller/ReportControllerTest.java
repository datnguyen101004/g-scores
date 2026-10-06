package com.dat.backend.controller;

import java.math.BigDecimal;
import java.net.URISyntaxException;
import java.nio.file.Path;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Types;
import java.util.Arrays;
import java.util.List;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;

import static org.hamcrest.Matchers.closeTo;
import static org.hamcrest.Matchers.hasSize;
import static org.hamcrest.Matchers.not;
import static org.hamcrest.Matchers.nullValue;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@Execution(ExecutionMode.SAME_THREAD)
@AutoConfigureMockMvc
@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ReportControllerTest {

    private static final String INSERT_SQL = """
            INSERT INTO exam_scores (
                sbd, toan, ngu_van, ngoai_ngu, vat_li, hoa_hoc, sinh_hoc, lich_su, dia_li, gdcd, ma_ngoai_ngu
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """;

    // This registry is deliberately fixed to the public API-to-entity score mapping.
    private static final List<SubjectColumn> SUBJECT_COLUMNS = List.of(
            new SubjectColumn("toan", 0),
            new SubjectColumn("nguVan", 1),
            new SubjectColumn("ngoaiNgu", 2),
            new SubjectColumn("vatLi", 3),
            new SubjectColumn("hoaHoc", 4),
            new SubjectColumn("sinhHoc", 5),
            new SubjectColumn("lichSu", 6),
            new SubjectColumn("diaLi", 7),
            new SubjectColumn("gdcd", 8));

    @Container
    private static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer("postgres:17-alpine");

    @Autowired
    private MockMvc mockMvc;
    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @DynamicPropertySource
    static void configureDatabase(DynamicPropertyRegistry registry) throws URISyntaxException {
        Path csv = Path.of(ReportControllerTest.class.getResource("/student-scores.csv").toURI());
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
        registry.add("app.seed.csv-path", csv::toString);
    }

    @BeforeEach
    void clearSeedAndPreviousFixture() {
        jdbcTemplate.update("DELETE FROM exam_scores");
    }

    @Test
    void filtersToanByEveryInclusiveAndExclusiveBoundaryAndExcludesNullScores() throws Exception {
        String[] scores = {"0.00", "3.99", "4.00", "5.99", "6.00", "7.99", "8.00", "10.00", null};
        for (int index = scores.length - 1; index >= 0; index--) {
            insert(sbd(index + 1), scoreVector(scores[index], null, null, null, null, null, null, null, null), null);
        }

        insert("00000010", scoreVector("8.00", null, null, null, null, null, null, null, null), null);
        insert("00000011", scoreVector("6.00", null, null, null, null, null, null, null, null), null);
        insert("00000012", scoreVector("7.50", null, null, null, null, null, null, null, null), null);
        insert("00000013", scoreVector("4.00", null, null, null, null, null, null, null, null), null);
        insert("00000014", scoreVector("5.00", null, null, null, null, null, null, null, null), null);
        insert("00000015", scoreVector("5.50", null, null, null, null, null, null, null, null), null);

        assertReport("toan", "GTE_8", 3);
        assertReport("toan", "FROM_6_TO_8", 4);
        assertReport("toan", "FROM_4_TO_6", 5);
        assertReport("toan", "LT_4", 2);
    }

    @Test
    void mapsEachSupportedSubjectToItsOwnScoreColumn() throws Exception {
        int studentNumber = 1;
        for (int index = 0; index < SUBJECT_COLUMNS.size(); index++) {
            SubjectColumn subject = SUBJECT_COLUMNS.get(index);
            BigDecimal[] scores = new BigDecimal[SUBJECT_COLUMNS.size()];
            Arrays.fill(scores, BigDecimal.ZERO);
            scores[subject.columnIndex()] = decimal("8.50");
            scores[(subject.columnIndex() + 1) % SUBJECT_COLUMNS.size()] = null;
            for (int duplicate = 0; duplicate <= index; duplicate++) {
                insert(sbd(studentNumber++), scores, null);
            }
        }

        for (int index = 0; index < SUBJECT_COLUMNS.size(); index++) {
            assertReport(SUBJECT_COLUMNS.get(index).apiKey(), "GTE_8", index + 1);
        }
    }

    @Test
    void countsAllMatchingStudentsWithoutReturningDetailsOrPagination() throws Exception {
        for (int index = 1; index <= 25; index++) {
            insert(sbd(index), scoreVector("8.50", null, null, null, null, null, null, null, null), null);
        }
        assertReport("toan", "GTE_8", 25);
    }

    @Test
    void returnsZeroForEmptyDatasetAndMissingOrOutOfBandScores() throws Exception {
        assertReport("toan", "LT_4", 0);
        insert("00000001", scoreVector(null, null, null, null, null, null, null, null, null), null);
        insert("00000002", scoreVector("6.00", null, null, null, null, null, null, null, null), null);
        assertReport("toan", "LT_4", 0);
        assertReport("toan", "GTE_8", 0);
    }

    @Test
    void rejectsMissingEmptyAndUnsupportedReportFilters() throws Exception {
        for (MockHttpServletRequestBuilder request : List.of(
                get("/api/reports/students").param("scoreBand", "GTE_8"),
                get("/api/reports/students").param("subject", "").param("scoreBand", "GTE_8"),
                get("/api/reports/students").param("subject", "physics").param("scoreBand", "GTE_8"),
                get("/api/reports/students").param("subject", "toan"),
                get("/api/reports/students").param("subject", "toan").param("scoreBand", ""),
                get("/api/reports/students").param("subject", "toan").param("scoreBand", "LTE_4"))) {
            assertBadRequest(request);
        }
    }

    @Test
    void returnsTenWholePointBucketsIncludingZeroAndTheFinalInclusiveTenWithEvenMedian() throws Exception {
        insert("00000001", scoreVector("0.00", null, null, null, null, null, null, null, null), null);
        insert("00000002", scoreVector("0.99", null, null, null, null, null, null, null, null), null);
        insert("00000003", scoreVector("1.00", null, null, null, null, null, null, null, null), null);
        insert("00000004", scoreVector("8.99", null, null, null, null, null, null, null, null), null);
        insert("00000005", scoreVector("9.00", null, null, null, null, null, null, null, null), null);
        insert("00000006", scoreVector("10.00", null, null, null, null, null, null, null, null), null);
        insert("00000007", scoreVector(null, null, null, null, null, null, null, null, null), null);

        MvcResult result = mockMvc.perform(get("/api/reports/distribution").param("subject", "toan"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.statusCode").value(200))
                .andExpect(jsonPath("$.data.subject").value("toan"))
                .andExpect(jsonPath("$.data.totalStudents").value(6))
                .andExpect(jsonPath("$.data.averageScore").value(closeTo(4.9966666667, 0.000001)))
                .andExpect(jsonPath("$.data.medianScore").value(closeTo(4.995, 0.000001)))
                .andExpect(jsonPath("$.data.bins", hasSize(10)))
                .andReturn();

        JsonNode data = objectMapper.readTree(result.getResponse().getContentAsString()).path("data");
        JsonNode bins = data.path("bins");
        int[] expectedCounts = new int[10];
        expectedCounts[0] = 2;
        expectedCounts[1] = 1;
        expectedCounts[8] = 1;
        expectedCounts[9] = 2;
        long histogramTotal = 0;
        for (int index = 0; index < bins.size(); index++) {
            JsonNode bin = bins.get(index);
            assertEquals(index, bin.path("lowerBound").asDouble());
            assertEquals(index + 1, bin.path("upperBound").asDouble());
            assertEquals(index == 9, bin.path("upperInclusive").asBoolean());
            assertEquals(expectedCounts[index], bin.path("count").asInt());
            histogramTotal += bin.path("count").asLong();
        }
        assertEquals(data.path("totalStudents").asLong(), histogramTotal);
    }

    @Test
    void returnsOddMedianForSelectedSubject() throws Exception {
        insert("00000001", scoreVector("1.00", null, null, null, null, null, null, null, null), null);
        insert("00000002", scoreVector("5.00", null, null, null, null, null, null, null, null), null);
        insert("00000003", scoreVector("9.00", null, null, null, null, null, null, null, null), null);

        mockMvc.perform(get("/api/reports/distribution").param("subject", "toan"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.totalStudents").value(3))
                .andExpect(jsonPath("$.data.averageScore").value(5.0))
                .andExpect(jsonPath("$.data.medianScore").value(5.0));
    }

    @Test
    void returnsTenEmptyBucketsAndNullMetricsWhenNoSubjectScoresExist() throws Exception {
        MvcResult result = mockMvc.perform(get("/api/reports/distribution").param("subject", "toan"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.totalStudents").value(0))
                .andExpect(jsonPath("$.data.averageScore").value(nullValue()))
                .andExpect(jsonPath("$.data.medianScore").value(nullValue()))
                .andExpect(jsonPath("$.data.bins", hasSize(10)))
                .andReturn();

        JsonNode bins = objectMapper.readTree(result.getResponse().getContentAsString()).path("data").path("bins");
        long histogramTotal = 0;
        for (JsonNode bin : bins) {
            assertEquals(0, bin.path("count").asInt());
            histogramTotal += bin.path("count").asLong();
        }
        assertEquals(0, histogramTotal);
    }

    @Test
    void mapsEachDistributionSubjectToItsOwnScoreColumn() throws Exception {
        for (int index = 0; index < SUBJECT_COLUMNS.size(); index++) {
            BigDecimal[] scores = new BigDecimal[SUBJECT_COLUMNS.size()];
            scores[index] = BigDecimal.valueOf(index + 1);
            insert(sbd(index + 1), scores, null);
        }

        for (int index = 0; index < SUBJECT_COLUMNS.size(); index++) {
            String subject = SUBJECT_COLUMNS.get(index).apiKey();
            double expectedScore = index + 1;
            mockMvc.perform(get("/api/reports/distribution").param("subject", subject))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.data.subject").value(subject))
                    .andExpect(jsonPath("$.data.totalStudents").value(1))
                    .andExpect(jsonPath("$.data.averageScore").value(expectedScore))
                    .andExpect(jsonPath("$.data.medianScore").value(expectedScore))
                    .andExpect(jsonPath("$.data.bins[" + (index + 1) + "].count").value(1));
        }
    }

    @Test
    void rejectsMissingEmptyAndUnsupportedDistributionSubjects() throws Exception {
        for (MockHttpServletRequestBuilder request : List.of(
                get("/api/reports/distribution"),
                get("/api/reports/distribution").param("subject", ""),
                get("/api/reports/distribution").param("subject", "physics"))) {
            mockMvc.perform(request)
                    .andExpect(status().isBadRequest())
                    .andExpect(jsonPath("$.statusCode").value(400))
                    .andExpect(jsonPath("$.path").value("/api/reports/distribution"))
                    .andExpect(jsonPath("$.message").isString())
                    .andExpect(jsonPath("$.message").value(not("")));
        }
    }

    private void assertReport(String subject, String scoreBand, long count) throws Exception {
        mockMvc.perform(get("/api/reports/students")
                        .param("subject", subject)
                        .param("scoreBand", scoreBand))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.statusCode").value(200))
                .andExpect(jsonPath("$.data.subject").value(subject))
                .andExpect(jsonPath("$.data.scoreBand").value(scoreBand))
                .andExpect(jsonPath("$.data.count").value(count))
                .andExpect(jsonPath("$.data.students").doesNotExist())
                .andExpect(jsonPath("$.data.page").doesNotExist())
                .andExpect(jsonPath("$.data.size").doesNotExist())
                .andExpect(jsonPath("$.data.totalElements").doesNotExist())
                .andExpect(jsonPath("$.data.totalPages").doesNotExist());
    }

    private void assertBadRequest(MockHttpServletRequestBuilder request) throws Exception {
        mockMvc.perform(request)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.statusCode").value(400))
                .andExpect(jsonPath("$.path").value("/api/reports/students"))
                .andExpect(jsonPath("$.message").isString())
                .andExpect(jsonPath("$.message").value(not("")));
    }


    private void insert(String sbd, BigDecimal[] scores, String maNgoaiNgu) {
        jdbcTemplate.update(connection -> {
            PreparedStatement statement = connection.prepareStatement(INSERT_SQL);
            statement.setString(1, sbd);
            for (int index = 0; index < scores.length; index++) {
                setNullableDecimal(statement, index + 2, scores[index]);
            }
            if (maNgoaiNgu == null) {
                statement.setNull(11, Types.VARCHAR);
            } else {
                statement.setString(11, maNgoaiNgu);
            }
            return statement;
        });
    }

    private static BigDecimal[] scoreVector(String... values) {
        BigDecimal[] scores = new BigDecimal[values.length];
        for (int index = 0; index < values.length; index++) {
            scores[index] = values[index] == null ? null : decimal(values[index]);
        }
        return scores;
    }

    private static void setNullableDecimal(PreparedStatement statement, int index, BigDecimal value) throws SQLException {
        if (value == null) {
            statement.setNull(index, Types.NUMERIC);
        } else {
            statement.setBigDecimal(index, value);
        }
    }

    private static BigDecimal decimal(String value) {
        return new BigDecimal(value);
    }

    private static String sbd(int number) {
        return "%08d".formatted(number);
    }

    private record SubjectColumn(String apiKey, int columnIndex) {
    }

}
