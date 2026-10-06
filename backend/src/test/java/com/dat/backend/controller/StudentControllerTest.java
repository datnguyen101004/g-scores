package com.dat.backend.controller;

import java.net.URISyntaxException;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.servlet.MockMvc;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.postgresql.PostgreSQLContainer;

import static org.hamcrest.Matchers.nullValue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
@Testcontainers
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class StudentControllerTest {

    @Container
    private static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer("postgres:17-alpine");

    @Autowired
    private MockMvc mockMvc;

    @DynamicPropertySource
    static void configureDatabase(DynamicPropertyRegistry registry) throws URISyntaxException {
        Path csv = Path.of(StudentControllerTest.class.getResource("/student-scores.csv").toURI());
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
        registry.add("app.seed.csv-path", csv::toString);
    }

    @Test
    void lookupPreservesLeadingZerosAndAllScoreFields() throws Exception {
        mockMvc.perform(get("/api/students/00000001"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.statusCode").value(200))
                .andExpect(jsonPath("$.length()").value(2))
                .andExpect(jsonPath("$.data.sbd").value("00000001"))
                .andExpect(jsonPath("$.data.toan").value(8.4))
                .andExpect(jsonPath("$.data.nguVan").value(6.75))
                .andExpect(jsonPath("$.data.ngoaiNgu").value(8.0))
                .andExpect(jsonPath("$.data.vatLi").value(6.0))
                .andExpect(jsonPath("$.data.hoaHoc").value(5.25))
                .andExpect(jsonPath("$.data.sinhHoc").value(5.0))
                .andExpect(jsonPath("$.data.lichSu").value(nullValue()))
                .andExpect(jsonPath("$.data.diaLi").value(nullValue()))
                .andExpect(jsonPath("$.data.gdcd").value(nullValue()))
                .andExpect(jsonPath("$.data.maNgoaiNgu").value("N1"));
    }

    @Test
    void absentSbdReturnsNotFound() throws Exception {
        mockMvc.perform(get("/api/students/99999999"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.statusCode").value(404))
                .andExpect(jsonPath("$.length()").value(4))
                .andExpect(jsonPath("$.message").isString())
                .andExpect(jsonPath("$.timestamp").isString());
    }

    @Test
    void sbdPrefixDoesNotMatchAStudent() throws Exception {
        mockMvc.perform(get("/api/students/0000000"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.statusCode").value(404));
    }

    @Test
    void listEndpointIsNoLongerAvailable() throws Exception {
        mockMvc.perform(get("/api/students"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.statusCode").value(500))
                .andExpect(jsonPath("$.data").doesNotExist());
    }

    @Test
    void unsupportedMethodUsesInternalServerErrorEnvelope() throws Exception {
        mockMvc.perform(post("/api/students/00000001"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.statusCode").value(500))
                .andExpect(jsonPath("$.length()").value(4))
                .andExpect(jsonPath("$.timestamp").isString());
    }

    @Test
    void unknownApiPathUsesErrorEnvelope() throws Exception {
        mockMvc.perform(get("/api/unknown-route"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.statusCode").value(500))
                .andExpect(jsonPath("$.length()").value(4))
                .andExpect(jsonPath("$.timestamp").isString());
    }

    @Test
    void unsupportedResponseFormatStillReturnsJsonError() throws Exception {
        mockMvc.perform(get("/api/students/00000001").accept("application/xml"))
                .andExpect(status().isInternalServerError())
                .andExpect(content().contentTypeCompatibleWith("application/json"))
                .andExpect(jsonPath("$.statusCode").value(500))
                .andExpect(jsonPath("$.length()").value(4))
                .andExpect(jsonPath("$.timestamp").isString());
    }
}
