package com.dat.backend.exception;

import java.time.Instant;

import com.jayway.jsonpath.JsonPath;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.TestComponent;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

class GlobalExceptionHandlerTest {

    @Test
    void unexpectedFailureReturnsTimestampedErrorWithoutInternalDetails() throws Exception {
        assertFailure(new IllegalStateException("sensitive-database-detail"), 500);
    }

    @Test
    void databaseFailureUsesFallbackWithoutExposingInternalDetails() throws Exception {
        assertFailure(new DataAccessResourceFailureException("sensitive-database-detail"), 500);
    }

    private void assertFailure(RuntimeException exception, int expectedStatus) throws Exception {
        MockMvc mockMvc = MockMvcBuilders.standaloneSetup(new FailureController(exception))
                .setControllerAdvice(new GlobalExceptionHandler())
                .build();
        MvcResult result = mockMvc.perform(get("/failure"))
                .andExpect(status().is(expectedStatus))
                .andExpect(jsonPath("$.statusCode").value(expectedStatus))
                .andExpect(jsonPath("$.length()").value(4))
                .andExpect(jsonPath("$.message").value(not(containsString("sensitive-database-detail"))))
                .andExpect(jsonPath("$.timestamp").isString())
                .andReturn();
        String timestamp = JsonPath.read(result.getResponse().getContentAsString(), "$.timestamp");
        Instant.parse(timestamp);
    }

    @TestComponent
    @RestController
    static class FailureController {

        private final RuntimeException exception;

        FailureController(RuntimeException exception) {
            this.exception = exception;
        }

        @GetMapping("/failure")
        public String fail() {
            throw exception;
        }
    }
}
