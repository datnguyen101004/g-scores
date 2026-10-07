package com.dat.backend.controller;

import java.math.BigDecimal;
import java.net.URISyntaxException;
import java.nio.file.Path;
import java.sql.PreparedStatement;
import java.sql.SQLException;
import java.sql.Types;
import java.util.Locale;

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
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;

import static org.hamcrest.Matchers.hasSize;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@Execution(ExecutionMode.SAME_THREAD)
@AutoConfigureMockMvc
@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class StudentRankingControllerTest {

    private static final String INSERT_SQL = """
            INSERT INTO exam_scores (
                sbd, toan, ngu_van, ngoai_ngu, vat_li, hoa_hoc, sinh_hoc, lich_su, dia_li, gdcd, ma_ngoai_ngu
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """;

    @Container
    private static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer("postgres:17-alpine");

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @DynamicPropertySource
    static void configureDatabase(DynamicPropertyRegistry registry) throws URISyntaxException {
        Path csv = Path.of(StudentRankingControllerTest.class.getResource("/student-scores.csv").toURI());
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
    void returnsACombinationSubjectsScoresAndTotal() throws Exception {
        insert("00000001", decimal("8.25"), decimal("4.50"), decimal("6.75"));

        mockMvc.perform(get("/api/students/top-10"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.statusCode").value(200))
                .andExpect(jsonPath("$.data.group").value("A"))
                .andExpect(jsonPath("$.data.subjects", hasSize(3)))
                .andExpect(jsonPath("$.data.subjects[0]").value("toan"))
                .andExpect(jsonPath("$.data.subjects[1]").value("vatLi"))
                .andExpect(jsonPath("$.data.subjects[2]").value("hoaHoc"))
                .andExpect(jsonPath("$.data.students", hasSize(1)))
                .andExpect(jsonPath("$.data.students[0].rank").value(1))
                .andExpect(jsonPath("$.data.students[0].sbd").value("00000001"))
                .andExpect(jsonPath("$.data.students[0].scores.toan").value(8.25))
                .andExpect(jsonPath("$.data.students[0].scores.vatLi").value(4.5))
                .andExpect(jsonPath("$.data.students[0].scores.hoaHoc").value(6.75))
                .andExpect(jsonPath("$.data.students[0].totalScore").value(19.5));
    }

    @Test
    void ranksEqualTotalsByHighestSubjectThenSbdKeepsZeroAndExcludesIncompleteScores() throws Exception {
        insert("00000003", decimal("9.00"), decimal("6.00"), decimal("5.00"));
        insert("00000002", BigDecimal.ZERO, decimal("10.00"), decimal("10.00"));
        insert("00000000", decimal("10.00"), decimal("5.00"), decimal("5.00"));
        insert("00000011", null, decimal("99.99"), decimal("99.99"));
        insert("00000012", decimal("99.99"), null, decimal("99.99"));
        insert("00000013", decimal("99.99"), decimal("99.99"), null);

        mockMvc.perform(get("/api/students/top-10"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.students", hasSize(3)))
                .andExpect(jsonPath("$.data.students[0].rank").value(1))
                .andExpect(jsonPath("$.data.students[0].sbd").value("00000000"))
                .andExpect(jsonPath("$.data.students[0].totalScore").value(20.0))
                .andExpect(jsonPath("$.data.students[1].rank").value(1))
                .andExpect(jsonPath("$.data.students[1].sbd").value("00000002"))
                .andExpect(jsonPath("$.data.students[1].scores.toan").value(0.0))
                .andExpect(jsonPath("$.data.students[1].totalScore").value(20.0))
                .andExpect(jsonPath("$.data.students[2].rank").value(3))
                .andExpect(jsonPath("$.data.students[2].sbd").value("00000003"))
                .andExpect(jsonPath("$.data.students[2].totalScore").value(20.0));
    }

    @Test
    void returnsOnlyTheTenHighestScoringStudentsInRankOrder() throws Exception {
        for (int points = 1; points <= 12; points++) {
            insert(String.format(Locale.ROOT, "%08d", points), BigDecimal.valueOf(points), BigDecimal.ONE, BigDecimal.ONE);
        }

        var result = mockMvc.perform(get("/api/students/top-10"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.students", hasSize(10)));
        for (int index = 0; index < 10; index++) {
            int points = 12 - index;
            result.andExpect(jsonPath("$.data.students[" + index + "].rank").value(index + 1))
                    .andExpect(jsonPath("$.data.students[" + index + "].sbd")
                            .value(String.format(Locale.ROOT, "%08d", points)))
                    .andExpect(jsonPath("$.data.students[" + index + "].totalScore").value(points + 2.0));
        }
    }

    @Test
    void highestSubjectWinsTheLastPlaceRegardlessOfWhichSubjectItIs() throws Exception {
        for (String highestSubject : new String[]{"toan", "vatLi", "hoaHoc"}) {
            jdbcTemplate.update("DELETE FROM exam_scores");
            for (int number = 1; number <= 9; number++) {
                insert(String.format(Locale.ROOT, "%08d", number),
                        decimal("9.00"), decimal("9.00"), decimal("9.00"));
            }
            insert("00000010", decimal("8.00"), decimal("8.00"), decimal("8.00"));
            insert("00000011",
                    decimal("toan".equals(highestSubject) ? "10.00" : "7.00"),
                    decimal("vatLi".equals(highestSubject) ? "10.00" : "7.00"),
                    decimal("hoaHoc".equals(highestSubject) ? "10.00" : "7.00"));

            mockMvc.perform(get("/api/students/top-10"))
                    .andExpect(status().isOk())
                    .andExpect(jsonPath("$.data.students", hasSize(10)))
                    .andExpect(jsonPath("$.data.students[0].totalScore").value(27.0))
                    .andExpect(jsonPath("$.data.students[9].rank").value(10))
                    .andExpect(jsonPath("$.data.students[9].sbd").value("00000011"))
                    .andExpect(jsonPath("$.data.students[9].totalScore").value(24.0));
        }
    }

    @Test
    void includesAllCutoffTiesButExcludesLowerHighestSubjectAndLowerTotal() throws Exception {
        for (int number = 1; number <= 9; number++) {
            insert(String.format(Locale.ROOT, "%08d", number),
                    decimal("9.00"), decimal("9.00"), decimal("9.00"));
        }
        insert("00000010", decimal("8.00"), decimal("8.00"), decimal("8.00"));
        insert("00000011", decimal("10.00"), decimal("7.00"), decimal("7.00"));
        insert("00000012", decimal("7.00"), decimal("10.00"), decimal("7.00"));
        insert("00000013", decimal("7.00"), decimal("7.00"), decimal("10.00"));
        insert("00000014", decimal("10.00"), decimal("6.00"), decimal("7.00"));

        mockMvc.perform(get("/api/students/top-10"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.students", hasSize(12)))
                .andExpect(jsonPath("$.data.students[0].rank").value(1))
                .andExpect(jsonPath("$.data.students[8].rank").value(1))
                .andExpect(jsonPath("$.data.students[9].rank").value(10))
                .andExpect(jsonPath("$.data.students[10].rank").value(10))
                .andExpect(jsonPath("$.data.students[11].rank").value(10))
                .andExpect(jsonPath("$.data.students[9].sbd").value("00000011"))
                .andExpect(jsonPath("$.data.students[10].sbd").value("00000012"))
                .andExpect(jsonPath("$.data.students[11].sbd").value("00000013"))
                .andExpect(jsonPath("$.data.students[11].totalScore").value(24.0));
    }

    @Test
    void returnsEmptyStudentsWhenNoStudentHasAllThreeACombinationScores() throws Exception {
        insert("00000001", decimal("9.00"), decimal("8.00"), null);

        mockMvc.perform(get("/api/students/top-10"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.statusCode").value(200))
                .andExpect(jsonPath("$.data.group").value("A"))
                .andExpect(jsonPath("$.data.students", hasSize(0)));
    }

    private void insert(String sbd, BigDecimal toan, BigDecimal vatLi, BigDecimal hoaHoc) {
        jdbcTemplate.update(connection -> {
            PreparedStatement statement = connection.prepareStatement(INSERT_SQL);
            statement.setString(1, sbd);
            setNullableDecimal(statement, 2, toan);
            statement.setNull(3, Types.NUMERIC);
            statement.setNull(4, Types.NUMERIC);
            setNullableDecimal(statement, 5, vatLi);
            setNullableDecimal(statement, 6, hoaHoc);
            statement.setNull(7, Types.NUMERIC);
            statement.setNull(8, Types.NUMERIC);
            statement.setNull(9, Types.NUMERIC);
            statement.setNull(10, Types.NUMERIC);
            statement.setNull(11, Types.VARCHAR);
            return statement;
        });
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
}
