package com.dat.backend.controller;

import java.net.URISyntaxException;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
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

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@ActiveProfiles("production")
@AutoConfigureMockMvc
@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ProductionReportCacheTest {

    private static final String TEST_PASSWORD = "isolated-cache-test-password";

    @Container
    private static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer("postgres:17-alpine");
    @Container
    private static final GenericContainer<?> REDIS = new GenericContainer<>("redis:7.4.2-alpine")
            .withCommand("redis-server", "--requirepass", TEST_PASSWORD)
            .withExposedPorts(6379);

    @Autowired
    private MockMvc mockMvc;
    @Autowired
    private JdbcTemplate jdbcTemplate;
    @Autowired
    private StringRedisTemplate redis;

    @DynamicPropertySource
    static void configureServices(DynamicPropertyRegistry registry) throws URISyntaxException {
        Path csv = Path.of(ProductionReportCacheTest.class.getResource("/student-scores.csv").toURI());
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
        registry.add("app.seed.csv-path", csv::toString);
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port", () -> REDIS.getMappedPort(6379));
        registry.add("spring.data.redis.password", () -> TEST_PASSWORD);
    }

    @Test
    void cachesThroughAuthenticatedRedisWithoutWritingIntoTheLocalNamespace() throws Exception {
        jdbcTemplate.update("DELETE FROM exam_scores");
        jdbcTemplate.update("INSERT INTO exam_scores (sbd, toan) VALUES ('00000001', 8.50)");
        String url = "/api/reports/students?subject=toan&scoreBand=GTE_8";
        mockMvc.perform(get(url)).andExpect(status().isOk()).andExpect(jsonPath("$.data.count").value(1));
        jdbcTemplate.update("UPDATE exam_scores SET toan = 0");
        mockMvc.perform(get(url)).andExpect(status().isOk()).andExpect(jsonPath("$.data.count").value(1));

        assertEquals(Boolean.TRUE, redis.hasKey("g-scores:production:v1:scoreCounts::toan:GTE_8"));
        assertEquals(Boolean.FALSE, redis.hasKey("g-scores:local:v1:scoreCounts::toan:GTE_8"));
    }
}
