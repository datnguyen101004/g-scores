package com.dat.backend.controller;

import java.net.URISyntaxException;
import java.nio.file.Path;
import java.time.Duration;

import tools.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.cache.CacheManager;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;

import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = "app.cache.ttl-seconds=3")
@ActiveProfiles("local")
@Execution(ExecutionMode.SAME_THREAD)
@AutoConfigureMockMvc
@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class LocalReportCacheTest {

    @Container
    private static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer("postgres:17-alpine");
    @Container
    private static final GenericContainer<?> REDIS = new GenericContainer<>("redis:7.4.2-alpine")
            .withExposedPorts(6379);

    @Autowired
    private MockMvc mockMvc;
    @Autowired
    private JdbcTemplate jdbcTemplate;
    @Autowired
    private CacheManager cacheManager;
    @Autowired
    private StringRedisTemplate redis;
    @Autowired
    private ObjectMapper objectMapper;

    @DynamicPropertySource
    static void configureServices(DynamicPropertyRegistry registry) throws URISyntaxException {
        Path csv = Path.of(LocalReportCacheTest.class.getResource("/student-scores.csv").toURI());
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
        registry.add("app.seed.csv-path", csv::toString);
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port", () -> REDIS.getMappedPort(6379));
    }

    @BeforeEach
    void resetIsolatedFixtureAndCaches() {
        cacheManager.getCacheNames().forEach(name -> cacheManager.getCache(name).clear());
        jdbcTemplate.update("DELETE FROM exam_scores");
        jdbcTemplate.update("""
                INSERT INTO exam_scores (sbd, toan, ngu_van, vat_li, hoa_hoc) VALUES
                ('00000001', 9.25, 2.50, 8.50, 8.75),
                ('00000002', 8.75, 3.50, 9.00, 7.50),
                ('00000003', 5.50, 9.50, 7.00, 6.50)
                """);
    }

    @Test
    void keepsSubjectsAndScoreBandsSeparateAndRoundTripsDistributionBuckets() throws Exception {
        mockMvc.perform(get(countUrl("toan", "GTE_8")))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.count").value(2));
        mockMvc.perform(get(countUrl("toan", "FROM_4_TO_6")))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.count").value(1));
        mockMvc.perform(get(countUrl("nguVan", "GTE_8")))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.count").value(1));
        String toan = response("/api/reports/distribution?subject=toan");
        String nguVan = response("/api/reports/distribution?subject=nguVan");

        jdbcTemplate.update("UPDATE exam_scores SET toan = 0, ngu_van = 0");

        mockMvc.perform(get(countUrl("toan", "GTE_8")))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.count").value(2));
        mockMvc.perform(get(countUrl("toan", "FROM_4_TO_6")))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.count").value(1));
        mockMvc.perform(get(countUrl("nguVan", "GTE_8")))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.count").value(1));
        assertEquals(objectMapper.readTree(toan),
                objectMapper.readTree(response("/api/reports/distribution?subject=toan")));
        assertEquals(objectMapper.readTree(nguVan),
                objectMapper.readTree(response("/api/reports/distribution?subject=nguVan")));
        mockMvc.perform(get("/api/reports/distribution?subject=invalid"))
                .andExpect(status().isBadRequest());
    }

    @Test
    void preservesRankedStudentsAndDecimalScoresAcrossRedisAndSupportsExplicitEviction() throws Exception {
        mockMvc.perform(get("/api/students/top-10"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.data.students[0].sbd").value("00000001"))
                .andExpect(jsonPath("$.data.students[0].rank").value(1))
                .andExpect(jsonPath("$.data.students[0].scores.toan").value(9.25))
                .andExpect(jsonPath("$.data.students[0].totalScore").value(26.5));
        String cachedRanking = response("/api/students/top-10");
        jdbcTemplate.update("DELETE FROM exam_scores");
        assertEquals(objectMapper.readTree(cachedRanking),
                objectMapper.readTree(response("/api/students/top-10")));

        cacheManager.getCache("topStudents").clear();
        mockMvc.perform(get("/api/students/top-10"))
                .andExpect(status().isOk()).andExpect(jsonPath("$.data.students").isEmpty());
    }

    @Test
    void refreshesChangedCountsAfterRedisEntryExpires() throws Exception {
        String url = countUrl("toan", "GTE_8");
        mockMvc.perform(get(url)).andExpect(status().isOk()).andExpect(jsonPath("$.data.count").value(2));
        jdbcTemplate.update("UPDATE exam_scores SET toan = 0");
        mockMvc.perform(get(url)).andExpect(status().isOk()).andExpect(jsonPath("$.data.count").value(2));

        await().atMost(Duration.ofSeconds(10)).until(() ->
                Boolean.FALSE.equals(redis.hasKey("g-scores:local:v1:scoreCounts::toan:GTE_8")));

        mockMvc.perform(get(url)).andExpect(status().isOk()).andExpect(jsonPath("$.data.count").value(0));
    }

    private String response(String url) throws Exception {
        return mockMvc.perform(get(url)).andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString();
    }

    private static String countUrl(String subject, String band) {
        return "/api/reports/students?subject=" + subject + "&scoreBand=" + band;
    }
}
