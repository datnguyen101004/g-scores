package com.dat.backend.config;

import java.time.Duration;
import java.util.Map;

import com.dat.backend.dto.ReportCountResponse;
import com.dat.backend.dto.ReportDistributionResponse;
import com.dat.backend.dto.TopStudentsResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;
import org.springframework.core.Ordered;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.cache.RedisCacheWriter;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.serializer.JacksonJsonRedisSerializer;
import org.springframework.data.redis.serializer.RedisSerializationContext.SerializationPair;

@Configuration(proxyBeanMethods = false)
@Profile({"local", "production"})
@EnableCaching(order = Ordered.HIGHEST_PRECEDENCE)
public class ReportCacheConfiguration {

    @Bean
    RedisCacheManager cacheManager(RedisConnectionFactory connectionFactory,
            @Value("${app.cache.ttl-seconds}") long ttlSeconds,
            @Value("${app.cache.key-prefix}") String keyPrefix) {
        if (ttlSeconds <= 0) {
            throw new IllegalArgumentException("app.cache.ttl-seconds must be positive");
        }
        RedisCacheConfiguration defaults = RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofSeconds(ttlSeconds))
                .disableCachingNullValues()
                .computePrefixWith(name -> keyPrefix + name + "::");
        // Complete Redis writes before returning, so an immediate read or eviction cannot race a pending write.
        RedisCacheWriter writer = RedisCacheWriter.create(connectionFactory, config -> config.immediateWrites());
        return RedisCacheManager.builder(writer)
                .cacheDefaults(defaults)
                .withInitialCacheConfigurations(Map.of(
                        "scoreDistributions", typedCache(defaults, ReportDistributionResponse.class),
                        "scoreCounts", typedCache(defaults, ReportCountResponse.class),
                        "topStudents", typedCache(defaults, TopStudentsResponse.class)))
                .disableCreateOnMissingCache()
                .build();
    }

    private static <T> RedisCacheConfiguration typedCache(RedisCacheConfiguration defaults, Class<T> type) {
        return defaults.serializeValuesWith(SerializationPair.fromSerializer(new JacksonJsonRedisSerializer<>(type)));
    }
}
